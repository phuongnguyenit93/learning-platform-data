# Cách virtual thread làm việc với socket và các thao tác chờ

Virtual thread giúp mã Java tiếp tục dùng các API blocking quen thuộc như Socket.read(), ServerSocket.accept() hoặc BlockingQueue.take() mà không nhất thiết giữ một platform thread trong toàn bộ thời gian chờ. Khi một thao tác blocking được JDK hỗ trợ có thể unmount virtual thread, JVM tạm dừng virtual thread đó và giải phóng carrier để chạy tác vụ khác.

Khi thao tác có thể tiếp tục, virtual thread được đưa trở lại scheduler và chạy tiếp, có thể trên một carrier khác. Cơ chế này giúp ứng dụng xử lý nhiều kết nối đồng thời theo mô hình thread-per-connection hoặc thread-per-request mà không cần tạo một OS thread cho mỗi kết nối.

Virtual thread không làm dữ liệu truyền qua mạng nhanh hơn và không rút ngắn thời gian phản hồi của server từ xa. Lợi ích chính là khả năng mở rộng và thông lượng của ứng dụng khi có nhiều tác vụ cùng chờ.

## 1. Virtual thread chờ socket như thế nào?

Một virtual thread không gắn cố định với một platform thread. Khi được chạy, nó được mount lên một carrier thread. Nếu virtual thread gọi một API socket blocking và hiện chưa có dữ liệu hoặc kết quả để tiếp tục, JDK có thể tạm dừng virtual thread và unmount nó khỏi carrier.

Quá trình có thể hình dung như sau:

~~~text
Virtual thread gọi Socket.read()
             |
             v
      Chưa có dữ liệu?
             |
             v
   Virtual thread được park
   và unmount khỏi carrier
             |
             v
   Carrier chạy virtual thread khác
             |
             v
      Socket có thể đọc?
             |
             v
   Scheduler đưa virtual thread
   trở lại hàng đợi thực thi
             |
             v
   Virtual thread mount lên carrier
   và tiếp tục từ vị trí đang chờ
~~~

Ứng dụng vẫn thấy lời gọi đồng bộ: read() chỉ trả về khi có dữ liệu, gặp EOF hoặc xảy ra lỗi. Việc đăng ký chờ I/O, unmount và lên lịch chạy lại do JDK/JVM quản lý. Không cần tự viết callback hoặc vòng lặp polling chỉ để nhường CPU.

Carrier được giải phóng trong lúc virtual thread chờ, nhưng kết nối socket và trạng thái của tác vụ vẫn được giữ. Khi dữ liệu sẵn sàng, virtual thread tiếp tục thực hiện phần mã sau lời gọi blocking.

## 2. Những thao tác socket được hỗ trợ

Trong Java 21, các API mạng trong java.net và java.nio.channels đã được cập nhật để làm việc với virtual thread. Các thao tác blocking tiêu biểu gồm:

| API | Thao tác có thể chờ | Ví dụ |
|---|---|---|
| Socket | Kết nối, đọc và ghi dữ liệu TCP | connect(), InputStream.read(), OutputStream.write() |
| ServerSocket | Chờ kết nối đến | accept() |
| DatagramSocket | Chờ datagram UDP | receive() |
| SocketChannel | Kết nối, đọc và ghi trong blocking mode | connect(), read(), write() |
| ServerSocketChannel | Chờ kết nối trong blocking mode | accept() |
| DatagramChannel | Nhận và gửi datagram trong blocking mode | receive(), send() |

Khi những thao tác này được gọi từ virtual thread, JDK có thể unmount virtual thread trong lúc chờ I/O. Với channel ở non-blocking mode, chương trình thường sử dụng selector hoặc cơ chế sự kiện; đây là một mô hình khác và không phải điều kiện cần để dùng virtual thread.

Không cần chuyển toàn bộ mã socket sang non-blocking chỉ vì ứng dụng đã dùng virtual thread. Với nhiều ứng dụng server, blocking API kết hợp một virtual thread cho mỗi kết nối hoặc request giúp mã đơn giản và dễ theo dõi hơn.

## 3. Ví dụ: đọc socket trong virtual thread

Ví dụ dưới đây kết nối tới một TCP service, gửi một dòng dữ liệu và chờ một dòng phản hồi. Các lời gọi connect() và readLine() có thể blocking; vì tác vụ chạy trong virtual thread, carrier có thể được dùng cho tác vụ khác trong lúc chờ socket:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualSocketClient {
    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> result = executor.submit(() -> {
                try (Socket socket = new Socket()) {
                    socket.connect(
                            new InetSocketAddress("service.example", 9000),
                            3_000
                    );
                    socket.setSoTimeout(5_000);

                    var reader = new BufferedReader(
                            new InputStreamReader(
                                    socket.getInputStream(),
                                    StandardCharsets.UTF_8
                            )
                    );
                    var writer = new BufferedWriter(
                            new OutputStreamWriter(
                                    socket.getOutputStream(),
                                    StandardCharsets.UTF_8
                            )
                    );

                    writer.write("PING");
                    writer.newLine();
                    writer.flush();

                    return reader.readLine();
                }
            });

            System.out.println(result.get());
        }
    }
}
~~~

Địa chỉ service.example:9000 đại diện cho một TCP service có thật trong môi trường triển khai. Ví dụ minh họa các điểm sau:

- connect() có thể chờ quá trình thiết lập kết nối; timeout giới hạn thời gian chờ.
- readLine() chờ dữ liệu đến hoặc EOF; trong lúc chờ, virtual thread có thể unmount.
- setSoTimeout() đặt giới hạn cho thao tác đọc socket; virtual thread vẫn có thể nhường carrier trong thời gian chờ.
- try-with-resources đóng socket khi tác vụ kết thúc, kể cả khi có lỗi.
- Nếu Future.get() được gọi từ một virtual thread, thao tác chờ kết quả cũng có thể park virtual thread và giải phóng carrier.

Trong mã sản phẩm, cần xử lý riêng timeout, lỗi kết nối, giao thức framing, kích thước dữ liệu và đóng socket khi request bị hủy.

## 4. Ví dụ: server nhận nhiều kết nối

Server thường cần chờ kết nối mới và xử lý nhiều client đồng thời. ServerSocket.accept() là lời gọi blocking. Mỗi socket được chấp nhận có thể được giao cho một virtual thread xử lý:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class VirtualSocketServer {
    static void handle(Socket socket) {
        try (socket) {
            var reader = new BufferedReader(
                     new InputStreamReader(
                             socket.getInputStream(),
                             StandardCharsets.UTF_8
                     ));
            var writer = new PrintWriter(
                     socket.getOutputStream(),
                     true,
                     StandardCharsets.UTF_8
             );

            String message = reader.readLine();
            if (message != null) {
                writer.println("Received: " + message);
            }
        } catch (IOException e) {
            // Ghi log hoặc xử lý lỗi của kết nối này.
        }
    }

    public static void main(String[] args) throws IOException {
        try (var server = new ServerSocket(8080);
             ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            while (!server.isClosed()) {
                Socket client = server.accept();
                executor.submit(() -> handle(client));
            }
        }
    }
}
~~~

Trong ví dụ, vòng lặp accept() chạy trên thread gọi main, còn mỗi handle() chạy trong virtual thread do executor tạo. Nếu vòng lặp accept cũng được chạy trong virtual thread, lời gọi accept() có thể unmount virtual thread đó trong khi chờ kết nối đến.

Mỗi handler có thể đọc hoặc ghi socket theo cách đồng bộ. Khi một client chưa gửi dữ liệu, handler tương ứng chờ mà không nhất thiết chiếm một carrier. Các handler khác vẫn có thể chạy trên carrier được giải phóng.

Ví dụ tập trung vào mô hình xử lý kết nối. Server thực tế cần có quy trình shutdown để đóng ServerSocket, kết thúc vòng accept, chờ các handler và đặt giới hạn tải đầu vào phù hợp.

## 5. Các thao tác chờ khác cũng có thể nhường carrier

Lợi ích của virtual thread không chỉ giới hạn ở socket. Nhiều API chờ trong JDK sử dụng cơ chế park để tạm dừng virtual thread. Một số ví dụ phổ biến:

| API | Tình huống chờ |
|---|---|
| Thread.sleep() | Chờ hết khoảng thời gian |
| LockSupport.park() | Chờ được unpark hoặc có sự kiện đánh thức |
| BlockingQueue.take() | Chờ phần tử xuất hiện trong queue |
| Semaphore.acquire() | Chờ permit |
| CountDownLatch.await() | Chờ bộ đếm về 0 |
| Future.get() | Chờ tác vụ hoàn tất |
| ReentrantLock.lock() | Chờ lấy khóa |

Ví dụ, một virtual thread có thể chờ thông điệp từ queue:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

BlockingQueue<String> queue = new LinkedBlockingQueue<>();

Thread worker = Thread.ofVirtual().start(() -> {
    try {
        String message = queue.take();
        process(message);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    }
});

queue.put("new message");
~~~

Khi queue rỗng, take() chờ cho đến khi có phần tử. Virtual thread có thể park và nhường carrier; khi phần tử được thêm, tác vụ được đánh thức và tiếp tục. Không cần tạo một platform thread riêng chỉ để ngồi chờ queue.

Các API này không thay thế quy tắc đồng bộ hóa hay quản lý tài nguyên. Ví dụ, Semaphore có thể giới hạn số tác vụ cùng truy cập một dịch vụ, còn BlockingQueue giúp trao đổi dữ liệu giữa producer và consumer.

## 6. Không phải mọi thao tác blocking đều unmount

Không nên suy luận rằng cứ gọi một API blocking thì virtual thread chắc chắn giải phóng carrier. Trong Java 21 có những trường hợp blocking vẫn giữ carrier:

- Nhiều thao tác filesystem hoặc file I/O phụ thuộc giới hạn của hệ điều hành và cách JDK triển khai; virtual thread có thể vẫn mounted trong khi chờ.
- Object.wait() là một trường hợp có giới hạn triển khai trong Java 21; thao tác có thể giữ carrier dù monitor được nhả trong lúc chờ.
- Nếu virtual thread thực hiện blocking khi đang ở trong synchronized block hoặc method, nó bị pin vào carrier.
- Khi virtual thread chạy native method hoặc foreign function, nó không thể unmount trong thời gian thực thi lời gọi đó.

Cần phân biệt hai hiện tượng:

| Hiện tượng | Điều xảy ra | Tác động |
|---|---|---|
| Blocking có unmount | Virtual thread được park và carrier được giải phóng | Carrier có thể chạy virtual thread khác |
| Blocking không unmount do giới hạn triển khai | Virtual thread vẫn mounted và carrier bị giữ | Scheduler có thể phải bù thêm carrier trong một số trường hợp |
| Pinning | Virtual thread không thể unmount do đang ở vùng synchronized hoặc native/foreign call | Carrier bị giữ; scheduler không bù cho pinning bằng cách mở rộng parallelism |

JEP 444 mô tả scheduler có thể tạm mở rộng parallelism để bù cho một số blocking không unmount được do giới hạn hệ điều hành hoặc JDK, chẳng hạn nhiều thao tác filesystem và Object.wait(). Cơ chế bù này không áp dụng cho pinning. Vì vậy, không nên đánh đồng mọi trường hợp carrier bị giữ với pinning.

Phần mô tả monitor pinning ở đây áp dụng cho runtime Java 21. Từ JDK 24, JEP 491 thay đổi cơ chế để virtual thread có thể unmount khi blocking trong synchronized block hoặc method. Khi chạy JDK mới hơn, cần đánh giá theo hành vi của runtime đó; không áp dụng cảnh báo riêng của Java 21 như một quy tắc chung cho mọi phiên bản.

## 7. Lưu ý về java.io stream trên socket trong Java 21

Ứng dụng thường dùng BufferedInputStream, BufferedOutputStream, BufferedReader, BufferedWriter, PrintStream hoặc PrintWriter để làm việc với socket stream.

Trong Java 21, các lớp JDK này đã được điều chỉnh để tránh pinning không cần thiết khi được dùng trực tiếp: chúng dùng explicit lock thay cho intrinsic monitor trong các đường xử lý tương ứng. Khi các lớp này được subclass, hành vi đồng bộ hóa trước đó vẫn được giữ.

Điều này không có nghĩa mọi mã tùy chỉnh dùng synchronized quanh stream đều an toàn cho khả năng unmount. Nếu ứng dụng tự giữ monitor trong lúc đọc hoặc ghi socket blocking, virtual thread vẫn có thể bị pin theo quy tắc Java 21.

Không chia sẻ cùng một InputStream, OutputStream, Reader hoặc Writer giữa nhiều tác vụ đồng thời nếu giao thức không định nghĩa rõ cách đồng bộ hóa. Các stream này không mặc nhiên bảo đảm mọi tổ hợp đọc/ghi đồng thời đều an toàn.

## 8. Interrupt và timeout khi chờ socket

Java 21 cập nhật các phương thức blocking I/O của Socket, ServerSocket và DatagramSocket để có thể interrupt khi được gọi trong virtual thread.

Nếu interrupt một virtual thread đang bị chặn trong thao tác I/O trên các loại socket này, thread được đánh thức và socket bị đóng. Vì socket bị đóng, ứng dụng không nên coi interrupt là cách tạm dừng một lần đọc rồi tiếp tục sử dụng cùng kết nối như chưa có gì xảy ra.

Ví dụ:

~~~java
Thread reader = Thread.ofVirtual().start(() -> {
    try (Socket socket = new Socket("service.example", 9000)) {
        int data = socket.getInputStream().read();
        System.out.println(data);
    } catch (IOException e) {
        // Xử lý lỗi I/O hoặc việc socket bị đóng khi interrupt.
    }
});

// Ở một luồng điều khiển khác:
reader.interrupt();
~~~

Với các API socket, việc interrupt có thể đóng socket và làm thao tác đang chờ kết thúc bằng lỗi I/O. Với SocketChannel và các channel kế thừa InterruptibleChannel, hành vi interruptible đã có từ trước; interruption trong lúc I/O blocking đóng channel theo hợp đồng của channel.

Timeout và interrupt giải quyết hai nhu cầu khác nhau:

- **Timeout** giới hạn thời gian chờ một thao tác, chẳng hạn Socket.connect(address, timeout) hoặc Socket.setSoTimeout(timeout) cho thao tác đọc.
- **Interrupt** báo cho tác vụ biết nó cần dừng; với socket blocking trong virtual thread Java 21, việc này còn đóng socket.

Ứng dụng nên có cả chính sách timeout và hủy tác vụ rõ ràng. Virtual thread làm cho việc chờ rẻ hơn về platform thread, nhưng không nên để kết nối hoặc request chờ vô hạn.

## 9. Backpressure và giới hạn tài nguyên

Virtual thread giúp quản lý số lượng lớn tác vụ đang chờ, nhưng không làm cho dịch vụ đích có khả năng xử lý vô hạn. Nếu hàng nghìn virtual thread cùng chờ kết nối hoặc cùng gửi request tới một database, hệ thống vẫn có thể cạn connection, bộ nhớ, socket hoặc quota.

Một số nguyên tắc thực tế:

- Dùng một virtual thread cho mỗi tác vụ hoặc kết nối khi mô hình blocking phù hợp; không cần pool virtual thread để tái sử dụng chúng.
- Giới hạn tài nguyên khan hiếm bằng connection pool, Semaphore, rate limiter hoặc giới hạn số request được nhận.
- Đặt connect timeout, read timeout và deadline ở tầng request.
- Đóng socket và response stream khi hoàn tất hoặc khi hủy tác vụ.
- Đo số kết nối đồng thời, số tác vụ chờ, thời gian chờ I/O, lỗi timeout và mức sử dụng bộ nhớ dưới tải đại diện.

Không dùng một executor virtual thread không giới hạn như một cơ chế backpressure. Nếu đầu vào có thể tăng nhanh hơn khả năng xử lý, cần có admission control hoặc giới hạn queue ở tầng ứng dụng.

## 10. Cách quan sát hành vi khi chạy

Khi kiểm tra một đường xử lý socket, có thể theo dõi:

1. Số virtual thread đang chạy và số virtual thread đang chờ.
2. Số carrier thread đang hoạt động.
3. Thời gian chờ connect, accept, read và write.
4. Số socket mở, connection pool và tỷ lệ timeout.
5. Sự kiện pinning nếu có vùng synchronized hoặc native call quanh thao tác blocking.

Java Flight Recorder có sự kiện jdk.VirtualThreadPinned để giúp phát hiện virtual thread bị pin trong thời gian dài. Với Java 21, có thể bật trace khi điều tra:

~~~shell
java -Djdk.tracePinnedThreads=full -jar application.jar
~~~

Chỉ bật trace khi cần chẩn đoán vì output có thể nhiều. Một thao tác file I/O hoặc Object.wait() giữ carrier không tự động đồng nghĩa với pinning; hãy xem stack trace và ngữ cảnh blocking để xác định nguyên nhân.

## 11. Tiêu chí áp dụng

| Câu hỏi | Hướng đánh giá |
|---|---|
| Tác vụ chờ socket connect, accept, read hoặc write? | Virtual thread thường phù hợp vì JDK 21 hỗ trợ unmount cho blocking network I/O |
| Tác vụ chờ queue, semaphore, latch hoặc future? | Các API chờ này thường park virtual thread và giải phóng carrier |
| Tác vụ chủ yếu chạy CPU liên tục? | Virtual thread không làm tăng năng lực CPU; giới hạn mức song song theo tài nguyên CPU |
| Tác vụ thực hiện file I/O hoặc Object.wait()? | Kiểm tra hành vi cụ thể vì Java 21 có trường hợp giữ carrier nhưng scheduler có thể bù |
| Tác vụ blocking bên trong synchronized hoặc native call? | Kiểm tra pinning vì carrier bị giữ và scheduler không bù cho pinning |
| Nhiều virtual thread cùng gọi một dịch vụ có quota? | Bổ sung giới hạn đồng thời và backpressure |
| Cần hủy một thao tác socket đang chờ? | Xem xét interrupt hoặc đóng socket; hiểu rằng interrupt có thể đóng socket |

Virtual thread phù hợp với socket và nhiều thao tác chờ vì ứng dụng có thể giữ cách viết blocking dễ đọc trong khi carrier được tái sử dụng. Để đạt khả năng mở rộng, cần hiểu chính xác thao tác nào unmount, thao tác nào giữ carrier, cách interrupt ảnh hưởng socket và giới hạn tài nguyên của hệ thống.

## Tài liệu tham khảo

- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [Oracle Java SE 21 API — Socket](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html)
- [Oracle Java SE 21 API — ServerSocket](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/ServerSocket.html)
- [Oracle Java SE 21 API — DatagramSocket](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/DatagramSocket.html)
