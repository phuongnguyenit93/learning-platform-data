# Ngắt, đóng từ luồng khác và hành vi phụ thuộc loại I/O trong Java

Một luồng Java có thể đang bị chặn trong `read()`, `write()`, `accept()` hoặc `select()` khi luồng khác yêu cầu dừng chương trình. Lúc này có nhiều cơ chế dễ bị nhầm:

- **`Thread.interrupt()`** đặt cờ ngắt của thread và có thể đánh thức một số thao tác chặn theo hợp đồng API.
- **`close()` từ luồng khác** đóng tài nguyên, có thể khiến thao tác I/O đang chờ kết thúc hoặc ném ngoại lệ.
- **Timeout** giới hạn thời gian chờ cho những thao tác hỗ trợ, thường không đồng nghĩa đóng tài nguyên.
- **EOF hoặc half-close** mô tả kết thúc luồng dữ liệu, không giống ngắt thread.
- **Cancellation** ở `Future`/`ExecutorService` là yêu cầu dừng tác vụ; hiệu lực của nó phụ thuộc loại tác vụ và API I/O.

**Không tồn tại một quy tắc chung rằng gọi `interrupt()` sẽ hủy ngay mọi `InputStream.read()`.** Java NIO có hợp đồng cụ thể cho `InterruptibleChannel`, trong khi một số luồng `java.io`, socket, console, file và thao tác selector hoạt động khác nhau. Bài này tập trung vào Java 17+, đặc biệt các platform thread truyền thống; những biến thể triển khai và virtual thread ở JDK mới hơn cần xem tài liệu đúng phiên bản.

## 1. Ba câu hỏi phải xác định trước khi hủy I/O

Trước khi viết logic dừng, hãy xác định:

1. **Luồng đang chặn trong API cụ thể nào?** Chẳng hạn `Socket.getInputStream().read()`, `SocketChannel.read()`, `Files.newInputStream(path).read()`, `ServerSocket.accept()` hay `Selector.select()`.
2. **Tài nguyên có thể được đóng an toàn bởi ai?** Thread xử lý có sở hữu tài nguyên không, hay tài nguyên dùng chung? Đóng tài nguyên dùng chung có thể làm hỏng các công việc khác.
3. **Điều gì là kết quả hợp lệ?** Dừng bằng ngoại lệ, trả EOF `-1`, trả số byte đã đọc, trả `0` hoặc thức dậy rồi tiếp tục vòng lặp đều mang ý nghĩa khác nhau.

Một thiết kế hủy đáng tin cậy nên mô tả rõ **tín hiệu hủy**, **cách giải phóng blocking call**, **cách làm sạch tài nguyên** và **cách báo nguyên nhân kết thúc**.

## 2. Thread.interrupt() thật sự làm gì?

`Thread.interrupt()` không ép thread chết và không “ném ngoại lệ” tùy ý vào mã đang chạy. Nó đặt **trạng thái interrupted**; với một số thao tác chờ có hợp đồng hỗ trợ ngắt, thao tác ấy sẽ dừng chờ. Ví dụ `Thread.sleep(...)`, `Object.wait(...)` và `Thread.join(...)` có thể ném `InterruptedException`, đồng thời **xóa trạng thái interrupted** khi ném ngoại lệ đó.

~~~java
// Mảnh mã minh họa: worker là một Thread đã tạo và đang chạy.
worker.interrupt();
~~~

Sau khi gọi, thread kia có dừng hay không còn phụ thuộc việc nó đang làm. Với vòng lặp CPU-bound, ứng dụng thường phải **tự kiểm tra cờ ngắt**:

~~~java
// Mảnh mã minh họa: điều kiện lặp và công việc được xác định ở nơi khác.
while (!Thread.currentThread().isInterrupted()) {
    // Thực hiện một đơn vị công việc có giới hạn.
}
~~~

`Thread.currentThread().isInterrupted()` chỉ **kiểm tra**, không xóa cờ. Ngược lại, `Thread.interrupted()` là phương thức tĩnh kiểm tra **và xóa** cờ ngắt của thread hiện tại. Vì vậy tránh gọi `Thread.interrupted()` ngẫu nhiên ở nơi không muốn tiêu thụ tín hiệu hủy.

Nếu phải bắt `InterruptedException` mà không thể truyền tiếp theo hợp đồng phương thức, cách thông dụng là phục hồi cờ và kết thúc công việc:

~~~java
try {
    worker.join();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Hủy hoặc trả quyền điều khiển cho tầng gọi thích hợp.
}
~~~

Đây là **mảnh mã minh họa**. Không nên nuốt `InterruptedException` rồi tiếp tục chờ vô hạn mà không chủ động xử lý hủy.

**Khác biệt cốt lõi:** có thể `interrupt()` khiến thao tác chặn trên một **channel** bị hủy theo hợp đồng NIO, nhưng điều đó **không chứng minh** mọi triển khai `InputStream` đều tuân theo cùng cách.

## 3. java.nio.channels.InterruptibleChannel: hợp đồng rõ ràng

`InterruptibleChannel` thuộc Java NIO đại diện cho channel vừa **có thể bị đóng từ luồng khác**, vừa **hỗ trợ ngắt khi thao tác I/O đang chặn**. Các lớp như `SocketChannel`, `ServerSocketChannel`, `FileChannel`, `Pipe.SourceChannel`, `Pipe.SinkChannel` triển khai giao diện này.

Hai trường hợp được đặc tả phân biệt rõ:

| Sự kiện tác động lên một thao tác blocking I/O trên InterruptibleChannel | Hành vi theo hợp đồng |
|---|---|
| **Thread khác gọi `channel.close()`** khi thao tác đang chặn | Thread đang chặn nhận `AsynchronousCloseException` |
| **Thread khác gọi `blockedThread.interrupt()`** khi thao tác đang chặn | Channel bị đóng; thread nhận `ClosedByInterruptException`; cờ interrupted được đặt |
| Thread đã có cờ interrupted trước khi bắt đầu blocking I/O trên channel | Channel bị đóng, nhận `ClosedByInterruptException` ngay; cờ vẫn được đặt |

`ClosedByInterruptException` **kế thừa** `AsynchronousCloseException`, còn `AsynchronousCloseException` kế thừa `ClosedChannelException`, và cả ba thuộc họ `IOException`. Nếu cần phân biệt nguyên nhân, hãy catch ngoại lệ **cụ thể hơn trước**:

~~~java
try {
    // Một lời gọi blocking read trên InterruptibleChannel đã mở.
} catch (ClosedByInterruptException ex) {
    // Được ngắt: channel đã đóng, cờ interrupt đặt.
} catch (AsynchronousCloseException ex) {
    // Bị đóng từ luồng khác trong khi chặn.
} catch (IOException ex) {
    // Những lỗi I/O còn lại.
}
~~~

Đây là **mảnh mã minh họa**, không phải chương trình độc lập. Bắt `AsynchronousCloseException` trước `ClosedByInterruptException` sẽ khiến nhánh riêng cho interrupt không bao giờ chạy.

Lưu ý:

- Ngoại lệ `ClosedByInterruptException` từ channel không phải `InterruptedException`. Đừng máy móc dự đoán trạng thái cờ qua tên ngoại lệ; trong hợp đồng `InterruptibleChannel`, cờ ngắt **được giữ ở trạng thái đặt**.
- Nếu channel đã đóng **trước** khi thread gọi `read()`, thông thường có thể nhận `ClosedChannelException` thay vì `AsynchronousCloseException`. Đây không phải lỗi logic của chương trình; hai thread thực thi cạnh tranh thời gian.
- Ngắt một channel chặn có thể **đóng hẳn channel**, không chỉ dừng một lời gọi `read` để có thể tái sử dụng ngay.
- Với channel ở chế độ **non-blocking**, lời gọi `read()`/`write()` có thể trả `0` khi chưa sẵn sàng, nên cách chờ/hủy phải xem logic vòng lặp hoặc `Selector`; không áp dụng mù quáng một kỳ vọng về blocking exception.

## 4. Ví dụ Java 17+: ngắt một Pipe.SourceChannel đang chờ đọc

Sử dụng `Pipe` trong NIO để tạo một nguồn đọc chưa có dữ liệu. Ta giữ sink mở nhưng không ghi byte nào; nhờ vậy read không gặp EOF từ việc đóng phía ghi. Thread chính yêu cầu ngắt worker, khiến channel đọc bị đóng theo hợp đồng `InterruptibleChannel`.

Tạo tệp **`InterruptChannelDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.ClosedByInterruptException;
import java.nio.channels.Pipe;
import java.util.concurrent.CountDownLatch;

public class InterruptChannelDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {
            CountDownLatch ready = new CountDownLatch(1);

            Thread worker = new Thread(() -> {
                ready.countDown();

                try {
                    source.read(ByteBuffer.allocate(1));
                    System.out.println("read completed");
                } catch (ClosedByInterruptException ex) {
                    System.out.println("ClosedByInterruptException");
                    System.out.println("interrupted="
                            + Thread.currentThread().isInterrupted());
                } catch (IOException ex) {
                    System.out.println("Unexpected I/O: "
                            + ex.getClass().getSimpleName());
                }
            });

            worker.start();
            ready.await();
            worker.interrupt();
            worker.join();

            System.out.println("channelOpen=" + source.isOpen());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 InterruptChannelDemo.java
java InterruptChannelDemo
~~~

Stdout theo hợp đồng NIO:

~~~text
ClosedByInterruptException
interrupted=true
channelOpen=false
~~~

**Tại sao kết quả ổn định?** `CountDownLatch` đảm bảo worker đã bắt đầu tác vụ trước khi main yêu cầu ngắt. Nếu main kịp `interrupt()` trước khi worker thực sự vào `source.read()`, cờ interrupted đã được đặt nên khi bắt đầu blocking read channel sẽ đóng và nhận cùng `ClosedByInterruptException`. Nếu worker đã blocking, interrupt làm thao tác ấy kết thúc với ngoại lệ tương tự.

- `source.read(ByteBuffer.allocate(1))` cần chờ vì pipe chưa có byte nào và `sink` còn mở.
- `interrupt()` không chỉ gây ngoại lệ; nó còn làm `source.isOpen()` trở thành `false`.
- `worker.join()` giúp main chờ worker kết thúc trước khi kiểm tra trạng thái channel.
- `try-with-resources` giải phóng cả hai phía pipe. Không dùng `Thread.sleep(...)` để đoán worker đã vào read; latch tránh phụ thuộc thời điểm lên lịch cho logic của demo.

Trong chương trình thật, cần bảo vệ `await()` và `join()` khỏi hủy của chính thread đang chờ: nếu bắt `InterruptedException`, thường nên phục hồi trạng thái ngắt và thực hiện cleanup theo chính sách ứng dụng.

## 5. Đóng channel từ luồng khác và vấn đề race

Khi luồng A gọi `source.close()` trong lúc luồng B chờ trên `source.read()`, `InterruptibleChannel` quy định B nhận `AsynchronousCloseException`. Nhưng nếu A đóng **trước khi** B bắt đầu `read()`, B có thể nhận `ClosedChannelException`. Vì vậy code thực tế không nên đòi một tên ngoại lệ cố định cho mọi cách sắp xếp thread.

Ví dụ độc lập **`CloseChannelDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.ClosedChannelException;
import java.nio.channels.Pipe;
import java.util.concurrent.CountDownLatch;

public class CloseChannelDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {
            CountDownLatch ready = new CountDownLatch(1);

            Thread worker = new Thread(() -> {
                ready.countDown();

                try {
                    source.read(ByteBuffer.allocate(1));
                    System.out.println("Read completed");
                } catch (ClosedChannelException ex) {
                    System.out.println("Stopped by channel close");
                } catch (IOException ex) {
                    System.out.println("Unexpected I/O");
                }
            });

            worker.start();
            ready.await();
            source.close();
            worker.join();

            System.out.println("channelOpen=" + source.isOpen());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CloseChannelDemo.java
java CloseChannelDemo
~~~

Stdout trong hai cách sắp xếp hợp lệ của thao tác đóng/đọc:

~~~text
Stopped by channel close
channelOpen=false
~~~

`ClosedChannelException` là lớp cha của `AsynchronousCloseException`; do đó chương trình minh họa bắt chung **cả trường hợp đóng trước đọc lẫn đóng trong lúc blocking read** và tránh phụ thuộc scheduler. `sink` còn mở cho đến cuối khối `try` nên không tạo EOF ngoài ý muốn.

Việc gọi `close()` nhiều lần trên `Channel` thông thường không có thêm tác dụng sau khi đã đóng. Tuy vậy, quyền đóng tài nguyên phải được phân định rõ: khi nhiều task dùng chung channel, việc một task hủy bằng `close` làm ảnh hưởng đến tất cả.

## 6. Socket kiểu java.net: close, read timeout và interrupt không giống nhau

`java.net.Socket` có hợp đồng riêng; không suy ra từ `FileInputStream` hay từ một bất kỳ subclass `InputStream`.

### 6.1. Đóng Socket từ thread khác

Trong Java 17, `Socket.close()` được đặc tả khiến thread đang bị chặn trong thao tác I/O trên socket đó ném `SocketException`. Đóng socket cũng đóng input và output stream gắn với nó, và socket đó không thể kết nối lại.

~~~java
// Mảnh mã minh họa: socket là java.net.Socket đang dùng bởi thread khác.
socket.close(); // Có thể đánh thức read đang bị chặn trên socket.
~~~

Đây là chiến lược hủy hữu ích khi task **sở hữu socket**. Nếu socket thuộc kết nối dùng chung, quyết định đóng phải thuộc thành phần quản lý kết nối; không để một task tùy tiện hủy công việc của task khác.

### 6.2. SO_TIMEOUT chỉ giới hạn lần chờ đọc

Với `Socket.setSoTimeout(milliseconds)` có giá trị dương, một lần `read()` qua input stream của socket chỉ chờ tối đa khoảng thời gian đó theo quy tắc socket. Khi hết thời gian, thao tác ném `SocketTimeoutException` nhưng **socket vẫn hợp lệ** và có thể tiếp tục dùng.

~~~java
// Mảnh mã minh họa: socket là Socket đang kết nối hợp lệ.
socket.setSoTimeout(2_000);

try {
    int value = socket.getInputStream().read();
    // value nằm trong 0..255 hoặc -1 ở EOF.
} catch (java.net.SocketTimeoutException ex) {
    // Hết thời gian chờ đọc; socket không tự bị đóng.
}
~~~

Đặt timeout trước thao tác blocking. Giá trị `0` của `SO_TIMEOUT` nghĩa là **không có giới hạn thời gian đọc** theo option này. `SocketTimeoutException` là subclass của `InterruptedIOException` nhưng **không nên đồng nhất timeout với việc thread bị `interrupt()`**.

Timeout của một lần read không tự thiết lập **deadline cho toàn bộ request**, bởi ứng dụng có thể thực hiện nhiều lượt đọc và mỗi lượt đều có một cửa sổ chờ mới. Muốn giới hạn tổng thời gian, phải theo dõi deadline hoặc sử dụng abstraction có thời hạn ở tầng thích hợp.

### 6.3. Socket qua SocketChannel có quy tắc NIO

Một `Socket` được tạo từ `SocketChannel` (chẳng hạn qua `SocketChannel.socket()`) có channel liên kết. Khi stream của nó ủy quyền thao tác cho channel, hành vi blocking interruption cũng tuân theo channel: ngắt thread đọc có thể đóng underlying channel và gây `ClosedByInterruptException`.

Ngược lại, không được khẳng định **mọi socket stream truyền thống trên mọi phiên bản Java đều hủy ngay bởi `Thread.interrupt()`**. Trên Java 17 với platform thread và socket không gắn channel, hãy dùng những biện pháp được tài liệu xác nhận như `Socket.close()`, `SO_TIMEOUT`, quản lý kết nối và kiểm thử trên môi trường đích. Các JDK có virtual thread từ Java 21 bổ sung những hành vi ngắt khác tùy loại socket/triển khai, cần tra tài liệu của JDK đó.

### 6.4. Half-close và EOF

`Socket.shutdownInput()` đặt phía đầu vào về trạng thái kết thúc, các lần đọc sau trả `-1` theo hợp đồng. `Socket.shutdownOutput()` dừng phía xuất, với TCP báo kết thúc gửi theo giao thức trong khi phía nhận vẫn có thể hoạt động. Đây là các thao tác **half-close**, không giống đóng toàn bộ socket bằng `close()`.

Một lần `read()` trả `-1` có nghĩa là **hết dữ liệu đầu vào**, không phải mặc nhiên thread bị ngắt. Đối tác mạng đóng phía gửi đúng quy trình cũng có thể khiến phía nhận thấy EOF. Phải tách kết thúc bình thường của giao thức khỏi lỗi và hủy.

## 7. ServerSocket.accept() và việc ngừng server

`ServerSocket.accept()` chặn để chờ kết nối đến. Với `ServerSocket` Java 17, luồng khác gọi `serverSocket.close()` sẽ khiến thread đang chờ `accept()` nhận `SocketException`. Đây là cách thường dùng để thoát vòng lặp chấp nhận kết nối khi shutdown.

~~~java
// Mảnh mã minh họa, không phải chương trình chạy độc lập.
try {
    while (!stopping) {
        Socket client = serverSocket.accept();
        // Giao client cho thành phần xử lý, xác định rõ ownership.
    }
} catch (java.net.SocketException ex) {
    if (!stopping) {
        throw ex; // Lỗi bất thường, không che giấu.
    }
}
~~~

Biến `stopping` là trạng thái dừng được chia sẻ đúng cách, thường dùng `volatile` hoặc primitive đồng bộ phù hợp. Khi shutdown: cập nhật trạng thái dừng rồi đóng `serverSocket`. Tuy nhiên một cờ boolean đơn thuần **không đánh thức** `accept()` đang chờ; chính `close()`/timeout hoặc một cơ chế được hỗ trợ mới đảm nhiệm việc đó.

`ServerSocket.setSoTimeout(...)` có thể giới hạn thời gian chờ `accept()`, khiến `SocketTimeoutException` xuất hiện nhưng server socket vẫn còn hợp lệ. Với một server lâu dài, không nhất thiết cần polling liên tục nếu đã có lối dừng an toàn bằng close.

## 8. Selector và non-blocking I/O lại là một cơ chế khác

`Selector.select()` không phải `SocketChannel.read()` đang chặn. Một thread đợi các channel sẵn sàng trong selector có thể được đánh thức bằng:

- `selector.wakeup()`: đánh thức thao tác select mà **không cần đóng** selector.
- `selector.close()`: đóng selector và đánh thức thao tác chọn đang chờ.
- `selectingThread.interrupt()`: đặt cờ interrupt và đánh thức select thông qua cơ chế wakeup.

**Đừng nhầm**: ngắt thread đang ở `Selector.select()` không có nghĩa là mọi channel đăng ký trong selector đều bị đóng như khi ngắt blocking I/O trực tiếp trên `InterruptibleChannel`.

Ví dụ một vòng event loop có cơ chế shutdown:

~~~java
// Mảnh mã minh họa: selector đã mở, running là cờ chia sẻ an toàn.
while (running) {
    selector.select();
    if (!running) {
        break;
    }
    // Xử lý các khóa đã sẵn sàng, sau đó loại/clear selected keys.
}

// Một thread quản lý yêu cầu dừng:
running = false;
selector.wakeup();
~~~

Nếu có nhiều luồng cùng thao tác với key/channel, cần tuân theo quy tắc đồng bộ của `Selector` và `SelectionKey`, đồng thời quản lý trạng thái đóng và key không còn hợp lệ.

### Non-blocking SocketChannel

Trong chế độ non-blocking, `SocketChannel.read(ByteBuffer)` có thể trả `0` khi chưa có dữ liệu. Đừng viết vòng `while (read(...) == 0) { }` quay CPU vô hạn để “chờ” dữ liệu. Dùng `Selector` hoặc cơ chế chờ phù hợp, tách riêng tín hiệu hủy khỏi trạng thái “chưa sẵn sàng”.

## 9. File I/O, bộ nhớ, pipe và console: không đánh đồng

| Loại nguồn/đích | Điều chắc chắn hoặc cần kiểm tra khi hủy |
|---|---|
| `FileChannel` (NIO) | Triển khai `InterruptibleChannel`; khi có thao tác blocking I/O thuộc hợp đồng này, interrupt có thể đóng channel và gây `ClosedByInterruptException` |
| `SocketChannel` / `ServerSocketChannel` blocking | NIO interruptible; phân biệt close từ thread khác và thread interrupt |
| `java.net.Socket` stream trên Java 17 | `Socket.close()` làm blocking socket I/O kết thúc bằng `SocketException`; `SO_TIMEOUT` giới hạn read |
| `java.net.ServerSocket.accept()` | `close()` từ thread khác đánh thức với `SocketException` |
| `ByteArrayInputStream`/`ByteArrayOutputStream` | Nằm hoàn toàn trong bộ nhớ, không đại diện cho thao tác chờ I/O bên ngoài; `interrupt()` không có nghĩa hủy một phép đọc buffer tức thời |
| `FileInputStream`/`FileOutputStream` truyền thống | Không có hợp đồng chung rằng `Thread.interrupt()` luôn hủy blocking I/O; hành vi phụ thuộc lời gọi và hệ thống/triển khai |
| `PipedInputStream`/`PipedOutputStream` | Các thao tác chờ và `close` có cơ chế riêng; có thể liên quan `InterruptedIOException` và đồng bộ, không đồng nhất với NIO Pipe |
| `System.in` hoặc console | Có thể phụ thuộc terminal/OS và wrapper; không bảo đảm ngắt hay đóng từ thread khác giải phóng mọi lần đọc |

Đừng dùng file I/O để minh họa một phép blocking chờ vô hạn rồi suy ra mọi loại file đều chờ như socket: đọc một file thường chỉ chặn ngắn, và thao tác cụ thể có thể hoàn tất trước khi yêu cầu hủy đến. Đồng thời, `close()` của một luồng I/O bất kỳ không mặc nhiên có tác dụng **đánh thức ngay** mọi thao tác đang bị chặn; cần xem tài liệu của loại tài nguyên thật đang sử dụng.

Nếu đang dùng wrapper như `BufferedInputStream`, `BufferedReader` hay `InputStreamReader`, phải xét cả **lớp bọc**, **đối tượng nguồn** và **cơ chế đồng bộ bên trong**. Đóng/interrupt ở một tầng không phải lúc nào cũng đi theo cùng đường truyền như kỳ vọng. Có API đồng bộ `close` với thao tác đọc, khiến việc đóng từ thread khác không phải lối hủy nhanh như trên `InterruptibleChannel`.

## 10. InterruptedIOException và xử lý phần dữ liệu đã truyền

`java.io.InterruptedIOException` báo một thao tác I/O bị gián đoạn theo hợp đồng API; trường `bytesTransferred` có thể cho biết số byte đã truyền thành công trước khi gián đoạn. `SocketTimeoutException` cũng kế thừa lớp này.

Nhưng phải nhớ:

- Không phải mọi hành vi ngắt đều tạo `InterruptedIOException`; NIO channel có `ClosedByInterruptException`.
- Không phải mọi `InterruptedIOException` đồng nghĩa thread có cờ interrupted; `SocketTimeoutException` có thể do timeout thông thường.
- Nếu thao tác ghi bị gián đoạn **sau khi đã ghi một phần**, gửi lại **toàn bộ** payload mà không xử lý tiến độ có thể tạo dữ liệu trùng. Nếu không biết chính xác phía nhận đã nhận gì, ứng dụng còn cần giao thức có sequence number, idempotency hoặc cách xác nhận riêng.
- Nếu thao tác đọc kết thúc sớm, không được giả định buffer chứa đủ số byte yêu cầu. Phải dựa vào giá trị trả về và hợp đồng của từng API.

Đọc ngoại lệ theo ngữ cảnh và trạng thái tài nguyên, thay vì chỉ kiểm tra `ex instanceof IOException` rồi thử lại không giới hạn.

## 11. Future.cancel(true) không phải nút dừng mọi I/O

Với `ExecutorService`, một lệnh như:

~~~java
// Mảnh mã minh họa: future đại diện cho task đã gửi.
future.cancel(true);
~~~

có ý nghĩa yêu cầu hủy tác vụ và **có thể ngắt thread đang thực hiện** nếu tác vụ đang chạy. Nó không bảo đảm một lời gọi `InputStream.read()` tùy ý sẽ lập tức kết thúc. Với blocking I/O không đáp ứng interrupt, task có thể vẫn giữ tài nguyên dù `Future` đã chuyển trạng thái cancelled.

Các bước thiết kế thường cần kết hợp:

1. Đặt **trạng thái hủy** mà vòng xử lý có thể quan sát.
2. Gọi `cancel(true)` hoặc `interrupt()` với những thao tác hỗ trợ.
3. **Đóng tài nguyên mà task sở hữu** nếu loại tài nguyên có hợp đồng đánh thức blocking call khi close.
4. Thiết lập **timeout/deadline** để giới hạn chờ, nếu API hỗ trợ.
5. Đợi task kết thúc và giải phóng tài nguyên với một giới hạn thời gian hợp lý, không đánh đổi bằng việc chờ vô hạn trên thread shutdown.

Đừng dùng `Thread.stop()` để giải quyết một lần đọc bị chặn: phương thức này không an toàn và đã bị loại khỏi cách thực hành hiện đại.

### Mẫu quản lý tài nguyên có trách nhiệm

Một phương án phổ biến là để task tự đóng nguồn bằng `try-with-resources` khi hoàn tất hoặc gặp lỗi; thành phần quản lý chỉ được gọi `close()` từ thread khác khi **được giao quyền sở hữu** để hủy một task cụ thể.

~~~java
// Mảnh mã minh họa: socket được tạo riêng cho task này,
// executor và Future<?> đã được quản lý ở tầng gọi.
Socket socket = new Socket();

try {
    // Thiết lập kết nối qua socket.connect(endpoint, connectTimeout).
    // Truyền socket vào task đọc và đặt read timeout nếu phù hợp.
    // Khi hủy, tầng quản lý có thể đóng socket do chính task sở hữu.
} finally {
    socket.close();
}
~~~

Chỉ riêng `Thread.interrupt()` thường không đủ để xác nhận tài nguyên đã đóng, đặc biệt với các loại I/O không implement `InterruptibleChannel`. Đồng thời cần tránh cạnh tranh khiến một thread đóng stream/channel khi thread khác vẫn đang sử dụng mà không được thiết kế cho việc đó.

## 12. Phân loại kết quả khi một read bị dừng

| Quan sát | Ý nghĩa cần cân nhắc | Cách xử lý |
|---|---|---|
| `read()` trả `-1` | Hết dữ liệu (EOF), phía gửi có thể đã half-close | Xử lý kết thúc thông thường theo giao thức |
| `read()` trả số byte dương | Đã nhận dữ liệu hợp lệ | Xử lý đúng số byte thực đọc |
| `read()` trả `0` | Có thể xảy ra với non-blocking channel hoặc lời gọi độ dài 0 | Không coi `0` là EOF; tránh busy-spin |
| `ClosedByInterruptException` | Blocking I/O trên interruptible channel bị ngắt, channel đóng | Dừng sử dụng channel, bảo toàn ý định hủy |
| `AsynchronousCloseException` | Channel bị đóng trong khi thao tác đang chặn | Kiểm tra shutdown hợp lệ hay lỗi bất ngờ |
| `ClosedChannelException` | Channel không còn mở cho thao tác | Kiểm tra lifecycle và race |
| `SocketException` khi đóng socket | Có thể là shutdown chủ đích hoặc lỗi mạng | Dựa vào trạng thái shutdown của ứng dụng để phân biệt |
| `SocketTimeoutException` | Hết thời gian chờ đọc/accept được cấu hình | Áp dụng retry/deadline theo nghiệp vụ; socket thường vẫn dùng được |
| `InterruptedException` | Một thao tác chờ có khả năng bị interrupt đã bị đánh thức | Truyền tiếp hoặc phục hồi cờ và kết thúc thích hợp |

Tránh viết code catch toàn bộ `IOException` rồi in “Đã hủy” vì có thể che giấu mất kết nối, quyền truy cập, hỏng thiết bị và lỗi dữ liệu. Ngược lại, một ngoại lệ sau khi shutdown chủ đích không nhất thiết là lỗi cần báo động: cần biết ngữ cảnh đóng tài nguyên.

## 13. Kiểm thử đúng cơ chế và tránh flaky test

Kiểm thử tình huống đồng thời phải có **đồng bộ rõ ràng**, không dựa vào `Thread.sleep(100)` để hy vọng thread kia đã blocking.

- Với `Pipe.SourceChannel`, giữ sink mở và không ghi byte để read có lý do chờ.
- Dùng `CountDownLatch` xác nhận thread xử lý đã chạy đến điểm chuẩn bị đọc; hợp đồng NIO còn cho phép xử lý trường hợp interrupt được đặt ngay trước khi gọi read.
- Đợi `join()`/`Future.get()` có giới hạn thích hợp trong test; nếu không kết thúc, dọn tài nguyên và thất bại có kiểm soát thay vì khiến bộ test treo.
- Khi test `close` từ thread khác, cho phép cả `AsynchronousCloseException` lẫn `ClosedChannelException` tùy close đến trước hay trong lúc blocking.
- Với socket, tạo kết nối loopback được kiểm soát và thử riêng timeout, close, EOF và half-close; không lấy thời gian phản hồi mạng bên ngoài làm bằng chứng cho thứ tự các thread.
- Kiểm tra **trạng thái** (`isOpen()`, `isClosed()`, cờ interrupted, dữ liệu đã nhận) bên cạnh loại exception.

Nếu chương trình vận hành trên nhiều JDK hoặc hệ điều hành, kiểm thử đúng **loại luồng đang sử dụng trong production**; một test với NIO `SocketChannel` không đại diện cho mọi wrapper `java.io` hoặc API mạng thế hệ khác.

## 14. Bảng quyết định nhanh

| Nhu cầu thực tế | Cơ chế thường phù hợp | Lưu ý |
|---|---|---|
| Hủy blocking NIO channel riêng của task | `interrupt()` hoặc `close()` theo chính sách tài nguyên | Interrupt cũng **đóng** `InterruptibleChannel` đang blocking |
| Dừng tác vụ đang `Socket.read()` (socket riêng) | `Socket.close()`; kết hợp `setSoTimeout` | `close` thường khiến `SocketException`; timeout không tự đóng |
| Dừng `ServerSocket.accept()` khi shutdown | Đặt cờ dừng và `ServerSocket.close()` | Không mong `volatile` flag tự đánh thức accept |
| Đánh thức event loop trong `Selector.select()` | `selector.wakeup()` | Không cần đóng selector/channel nếu chỉ muốn kiểm tra nhiệm vụ mới |
| Hủy task trên executor | `Future.cancel(true)` + cleanup/timeout | Cancellation không phải bảo đảm hủy mọi I/O |
| Xử lý tệp dài | Các khối đọc/ghi có điểm kiểm tra hủy | Đừng giả định file stream đáp ứng interrupt như NIO |
| Nhận EOF từ peer | Xử lý kết thúc giao thức | EOF không đồng nghĩa bị interrupt |
| Ứng dụng cần deadline toàn phần | Theo dõi thời hạn xuyên suốt các lần read/write | Timeout của từng read chưa chắc giới hạn toàn bộ nhiệm vụ |

## 15. Ghi nhớ cốt lõi

1. **`interrupt` là tín hiệu phối hợp hủy**, không phải cơ chế ép mọi Java thread hoặc I/O dừng ngay.
2. **`InterruptibleChannel`** có hợp đồng mạnh: ngắt thread đang blocking → channel đóng, `ClosedByInterruptException`, cờ interrupted đặt; close từ thread khác trong lúc blocking → `AsynchronousCloseException`.
3. **`Socket.close()`** và **`ServerSocket.close()`** trên Java 17 có quy tắc đánh thức blocking I/O tương ứng; `SO_TIMEOUT` ném timeout mà thường vẫn giữ socket hợp lệ.
4. **`Selector.select()`** có thể được đánh thức bằng `wakeup()` hoặc interrupt mà không mặc nhiên đóng tất cả channel đã đăng ký.
5. **`EOF (-1)`, timeout, interrupt, asynchronous close và lỗi I/O** có ý nghĩa khác nhau; không gộp mọi trường hợp thành “đã hủy”.
6. **Hủy tác vụ và đóng tài nguyên phải tuân theo ownership**: tránh đóng một tài nguyên dùng chung chỉ vì một worker không còn cần nó.
7. Xác minh chính xác hợp đồng của API/JDK đang dùng và kiểm thử bằng đồng bộ xác định thay vì `sleep` ngẫu nhiên.

### Tài liệu tham khảo chính thức

- [Java 17 — InterruptibleChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/InterruptibleChannel.html)
- [Java 17 — ClosedByInterruptException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ClosedByInterruptException.html)
- [Java 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [Java 17 — ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html)
- [Java 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
- [Java 17 — InterruptedIOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InterruptedIOException.html)
