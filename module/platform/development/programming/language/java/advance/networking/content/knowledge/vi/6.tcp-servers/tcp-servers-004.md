# Tách socket lắng nghe khỏi socket phục vụ từng máy khách trong TCP Server (Java)

Một máy chủ TCP thường có **một `ServerSocket` đang lắng nghe** và nhiều **`Socket` đang phục vụ các máy khách đã kết nối**. Chúng có quan hệ qua `accept()`, nhưng **không phải cùng một socket, không có cùng vòng đời và không thể đóng thay cho nhau**. Hiểu ranh giới này giúp xây dựng TCP server phục vụ nhiều client mà không làm rò tài nguyên hoặc vô tình cắt kết nối.

Ví dụ, server đang lắng nghe tại `127.0.0.1:9000`. Client A kết nối, server có một socket riêng để trao đổi dữ liệu với A. Client B kết nối sau đó, server lại có một socket riêng cho B. `ServerSocket` tiếp tục đảm nhận việc đợi kết nối mới. **Đóng socket của A không đóng listener hoặc socket của B; đóng listener không tự đóng các socket A/B đã được chấp nhận.**

Bài học này thuộc chủ đề **Máy chủ TCP** và tập trung trực tiếp vào việc phân biệt socket lắng nghe với socket xử lý từng client, từ cấu trúc, code đến shutdown. Các ví dụ dùng `java.net`, TCP blocking và Java 17+; không cần framework hoặc kết nối Internet.

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vai trò của `ServerSocket.bind()` và `ServerSocket.accept()`, cũng như đối tượng `Socket` trả về.
- Phân biệt local endpoint của listener với local/remote endpoint của kết nối đã accept.
- Tổ chức một accept loop giữ listener mở trong khi mỗi accepted socket có scope riêng.
- Chọn đúng nơi dùng `try-with-resources`, tránh đóng socket trước khi worker xử lý xong.
- Giải thích vì sao đóng listener không đóng accepted connections và ngược lại.
- Tách timeout/lỗi ở tầng accept khỏi timeout/lỗi của từng client.
- Thiết kế chuyển ownership, giới hạn concurrency và dừng TCP server có kiểm soát.
- Chạy hai chương trình Java độc lập chứng minh quan hệ vòng đời giữa listener và accepted socket.

## 2. Sơ đồ: một listener, nhiều kết nối

~~~text
                            TCP SERVER
                     +----------------------+
                     | ServerSocket         |
                     | local :9000          |
                     | accept()             |
                     +----------+-----------+
                                |
                +---------------+---------------+
                |                               |
             accept A                        accept B
                |                               |
         +------+--------+               +------+--------+
         | Socket A      |               | Socket B      |
         | local :9000   |               | local :9000   |
         | remote A:pa   |               | remote B:pb   |
         +------+--------+               +------+--------+
                |                               |
        InputStream/OutputStream       InputStream/OutputStream
                |                               |
             Client A                        Client B

close(Socket A): đóng A; listener và B không tự đóng.
close(listener): dừng nhận kết nối mới; A và B đã accepted
                 không bị đóng tự động.
~~~

Đối tượng Java cần phân biệt:

| Loại | Vai trò | Phương thức điển hình | Phạm vi sống |
| --- | --- | --- | --- |
| `ServerSocket` | Bind/lắng nghe TCP và chấp nhận client mới | `bind()`, `accept()`, `getLocalPort()`, `close()` | Vòng đời server/listener |
| `Socket` server-side từ `accept()` | Một TCP connection đã được chấp nhận | `getInputStream()`, `getOutputStream()`, `getRemoteSocketAddress()`, `close()` | Vòng đời một connection |
| `Socket` phía client | Đầu kia của TCP connection | `connect()`, `getInputStream()`, `getOutputStream()`, `close()` | Vòng đời client connection |

**Quan trọng:** `ServerSocket` không có `getInputStream()` hoặc `getOutputStream()` để đọc request của một client. Dữ liệu ứng dụng phải được đọc/ghi trên **accepted `Socket`**. Mỗi lần `accept()` trả về thành công là một connection riêng; server giữ listener để có thể accept lần tiếp theo.

## 3. Lắng nghe bằng `ServerSocket`: bind và accept

### 3.1. Khởi tạo listener

~~~java
ServerSocket listener = new ServerSocket();
listener.bind(new InetSocketAddress(
        InetAddress.getLoopbackAddress(), 9000), 64);
~~~

Đây là **mảnh code trong phương thức** (cần `import java.net.ServerSocket;`, `InetSocketAddress`, `InetAddress` và xử lý/khai báo `IOException`). Port 9000 chỉ là ví dụ; có thể không bind được nếu port đã bị sử dụng.

- `bind()` gắn listener với địa chỉ/port cục bộ. Với loopback, demo chỉ mở dịch vụ cho chương trình trên chính máy đó.
- Port `0` yêu cầu hệ điều hành chọn một port khả dụng; sau bind gọi `listener.getLocalPort()` để biết port thực tế.
- `backlog` là tham số cho hàng đợi kết nối đang chờ được accept theo hỗ trợ của OS. Nó **không** phải giới hạn số client phục vụ trong suốt vòng đời và cũng không phải kích thước thread pool.
- Nếu bind thất bại (`BindException` hoặc `IOException` khác), server chưa có endpoint lắng nghe hợp lệ. Phải xử lý cấu hình/port thay vì giả định đã sẵn sàng.
- Constructor `new ServerSocket(port)` hoặc `new ServerSocket(port, backlog, bindAddr)` cũng có thể bind ngay; `new ServerSocket()` + `bind()` giúp tách cấu hình và khởi tạo.

### 3.2. `accept()` tạo connection endpoint mới

~~~java
Socket accepted = listener.accept();
~~~

Trong mô hình blocking, `accept()` chờ đến khi có một client thiết lập kết nối hoặc phát sinh timeout/lỗi. Giá trị trả về là một **đối tượng `Socket` mới** cho connection đã accept, không phải chính `listener`.

Trong khi `accepted` đang đọc/ghi dữ liệu, listener vẫn còn được bind nếu chưa đóng. Khi cần phục vụ thêm client, mã server gọi `accept()` tiếp. Một accept **không tự đọc dữ liệu ứng dụng**; TCP chỉ đã thiết lập đường truyền byte.

Ví dụ accept loop đơn giản:

~~~java
try (ServerSocket listener = new ServerSocket(9000)) {
    while (running) {
        try (Socket accepted = listener.accept()) {
            handleClient(accepted);
        }
    }
}
~~~

Đây là **mã minh họa**, không phải chương trình độc lập: `running` và `handleClient` do ứng dụng cung cấp; cần xử lý `IOException`. Vì handler chạy **ngay trên thread accept**, server này xử lý các client **tuần tự**, không phục vụ đồng thời. Nó minh họa lifecycle đúng nhưng không phải cách duy nhất để xử lý nhiều client.

### 3.3. Vì sao nhiều accepted sockets vẫn dùng chung server port?

Giả sử listener ở `192.0.2.10:9000`; client A ở `198.51.100.11:51001`, B ở `198.51.100.12:51002`:

~~~text
Listener local endpoint: 192.0.2.10:9000

Accepted A:
    local  = 192.0.2.10:9000
    remote = 198.51.100.11:51001

Accepted B:
    local  = 192.0.2.10:9000
    remote = 198.51.100.12:51002
~~~

Các IP trên thuộc dải dành cho tài liệu, không phải endpoint chạy thật. TCP phân biệt kết nối bằng bộ bốn `(local IP, local port, remote IP, remote port)`. Các accepted sockets có thể cùng **local port** của server nhưng remote endpoint khác nhau, nên không trộn byte stream của nhau.

Trong code:

~~~java
listener.getLocalSocketAddress();  // endpoint listener
accepted.getLocalSocketAddress();  // endpoint local của kết nối này
accepted.getRemoteSocketAddress(); // client tương ứng
accepted.getLocalPort();           // port cục bộ, thường bằng port listener
accepted.getPort();                // REMOTE port của client
~~~

Đây là **mảnh code minh họa** với các biến đã được tạo. Đừng nhầm `accepted.getPort()` là port listener: trên `Socket`, nó là **remote port**. Không hard-code port động trong stdout test vì OS có thể chọn giá trị khác theo lần chạy.

## 4. Vòng đời và ownership là hai cấp khác nhau

Một TCP server cần định nghĩa trách nhiệm đóng tài nguyên:

1. **Server manager sở hữu listener**: tạo, bind, bắt đầu accept, dừng accept và đóng `ServerSocket`.
2. **Connection handler sở hữu accepted socket**: đọc request, ghi response, đóng `Socket` tương ứng khi giao dịch hoặc phiên kết thúc.

~~~text
Server scope:
    create/bind listener
    while receiving new clients:
        accepted = listener.accept()
        transfer ownership to handler
    close listener

Per-client handler scope:
    try (accepted) {
        read this client's bytes
        process its protocol
        write reply
    }
    // accepted.close() happens here
~~~

Nếu code gọi `handleClient(accepted)` đồng bộ, caller có thể dùng `try (Socket accepted = listener.accept())` để đóng sau handler. Nếu giao accepted socket cho worker bất đồng bộ, worker phải giữ resource scope trong chính handler. Không được dùng một `try (accepted)` ở caller rồi trả về ngay sau `executor.submit()`.

### 4.1. Lỗi đóng socket quá sớm khi giao cho executor

~~~java
// SAI nếu handler chưa chạy xong:
try (Socket accepted = listener.accept()) {
    executor.submit(() -> handleClient(accepted));
} // accepted.close() ngay sau submit!
~~~

`submit()` chỉ ghi nhận công việc cần chạy. Khi `try` của caller kết thúc, accepted socket bị đóng dù task chưa bắt đầu, hoặc đang đọc/ghi. `SocketException`, EOF sớm và response hỏng có thể xuất hiện khó tái hiện.

Mẫu ownership được chuyển cho worker (đoạn minh họa; các tên helper có sẵn ở nơi khác):

~~~java
Socket accepted = listener.accept();
try {
    executor.execute(() -> {
        try (accepted) {
            handleClient(accepted);
        } catch (IOException error) {
            logConnectionError(error);
        }
    });
} catch (RejectedExecutionException rejected) {
    try {
        accepted.close();
    } catch (IOException closeError) {
        rejected.addSuppressed(closeError);
    }
    throw rejected;
}
~~~

Đoạn này cần `Socket`, `IOException` và `RejectedExecutionException`; `listener`, `executor`, `handleClient` và `logConnectionError` do ứng dụng khai báo. Quy tắc: khi giao task thành công, handler sở hữu socket; khi executor từ chối, caller **vẫn phải đóng socket**. Có thể phải xử lý thêm runtime exceptions/logging và chính sách quá tải trong sản phẩm thực.

### 4.2. Tách `try-with-resources` theo lifetime

~~~text
try (listener) {             <-- scope sống qua nhiều lượt accept
    accept A
    handler A: try (A) { ... }   <-- đóng A khi xử lý A xong
    accept B
    handler B: try (B) { ... }   <-- đóng B độc lập
}                              <-- listener chỉ đóng cuối scope
~~~

Không nhất thiết mọi connection chỉ có một request. Một protocol có thể cho phép nhiều request liên tiếp trên cùng TCP connection; handler giữ accepted socket trong vòng đời **connection**, không đóng mỗi khi thấy một frame nếu protocol còn cần dùng socket.

## 5. Đóng listener khác đóng accepted socket

### 5.1. Đóng accepted socket

`accepted.close()` kết thúc **connection đó**. Nó đóng các stream của accepted socket và không đóng `ServerSocket` đang lắng nghe, không tự ảnh hưởng connection B/C. Đóng `InputStream` hoặc `OutputStream` lấy trực tiếp từ socket cũng đóng chính socket đó, vì vậy tránh đóng stream trước khi giao tiếp hai chiều kết thúc.

Với socket đã đóng:

- `accepted.isClosed()` là `true`.
- `accepted.isConnected()` có thể vẫn là `true` vì ghi nhận đã từng kết nối; nó **không** là kiểm tra peer còn sống.
- Một lần `close()` không bảo đảm peer đã xử lý xong dữ liệu vừa ghi. Nếu nghiệp vụ cần xác nhận, phải có ACK/response ở tầng ứng dụng.

### 5.2. Đóng listener

`listener.close()` đóng **endpoint lắng nghe**. Một thread đang chờ `listener.accept()` có thể bị giải phóng bằng `SocketException` vì listener đóng. Không thể `accept()` thêm trên listener đã đóng.

Nhưng **accepted socket đã tồn tại là độc lập**: server có thể cho những request đang chạy hoàn tất sau khi listener đóng. Đây là cơ chế quan trọng cho graceful shutdown: dừng nhận kết nối mới nhưng tiếp tục phục vụ kết nối cũ trong thời hạn nhất định.

Nếu muốn dừng cưỡng bức cả client cũ, server còn phải đóng accepted sockets do mình sở hữu, hoặc yêu cầu handler hợp tác hủy. Chỉ đóng listener **không giải phóng mọi file descriptor và worker của connection đang chạy**.

### 5.3. Bảng so sánh hành động

| Thao tác | Có nhận kết nối mới không? | Tác động tới accepted connections |
| --- | --- | --- |
| `acceptedA.close()` | Có, nếu listener vẫn mở | Chỉ A bị đóng; B không tự đóng theo |
| `listener.close()` | Không trên listener đó | A/B đã accept có thể tiếp tục I/O |
| `acceptedA.shutdownOutput()` | Listener không bị ảnh hưởng | Kết thúc **chiều gửi** của A; vẫn có thể đọc A |
| `executor.shutdown()` | Tùy accept loop, không tự đóng listener | Task đã nhận có cơ hội hoàn tất |
| `executor.shutdownNow()` | Không tự đóng listener | Gửi yêu cầu interrupt; không chắc đóng I/O blocking |
| Thoát `try (listener)` | Listener đóng | Accepted sockets cần lifecycle riêng |

`shutdownOutput()`/`shutdownInput()` là **half-close một hướng** của một `Socket`, không phải lệnh shutdown một TCP server. Với dữ liệu buffered, phải flush theo protocol trước khi half-close nếu cần gửi hết request.

## 6. Accept loop: tuần tự, thread pool và backpressure

### 6.1. Tuần tự

~~~text
accept A -> handle A -> close A
accept B -> handle B -> close B
accept C -> handle C -> close C
~~~

Ưu điểm: dễ đọc, đơn giản, không cần đồng bộ trạng thái nhiều handler. Hạn chế: client A chậm có thể giữ thread accept ở `read()`, khiến B/C phải chờ được xử lý, dù OS có thể đang xếp một số connection trong backlog.

### 6.2. Tách thread accept khỏi worker

~~~text
                  [ServerSocket]
                       |
                    accept()
                       |
           +-----------+------------+
           |           |            |
        Socket A    Socket B      Socket C
           |           |            |
        Worker A    Worker B      Worker C
           |           |            |
        close A     close B       close C

Accept loop tiếp tục dùng cùng listener.
~~~

Các worker có thể là platform threads, thread pool, virtual threads ở Java 21+, hoặc event loop với `java.nio.channels` theo kiến trúc khác. Mục đích ở đây là **tách công việc đón connection khỏi công việc đọc/ghi của từng client**.

Không có nghĩa mỗi client bắt buộc phải có một thread vĩnh viễn. Cần giới hạn concurrency:

- Một thread pool nhỏ có thể bảo vệ CPU nhưng queue không giới hạn vẫn cho phép số accepted sockets đang chờ tăng quá lớn.
- Queue hữu hạn và chính sách từ chối/hạn chế tải cần đi cùng việc **đóng socket vừa accepted khi không thể xử lý**.
- Virtual threads (Java 21+) giảm chi phí thread khi nhiều thao tác chờ I/O, nhưng vẫn phải giới hạn file descriptor, RAM, kích thước message và số việc gọi downstream.
- NIO/`Selector` có thể quản lý nhiều connection ở event loop, nhưng accepted channel và listener channel vẫn là hai vai trò tách biệt.

`backlog` **không phải** giới hạn số accepted sockets active, cũng không tự thay thế rate limiting hoặc giới hạn resource của ứng dụng.

## 7. Ví dụ 1 chạy được: một listener phục vụ hai client

Ví dụ tự bind vào loopback và port `0` để OS chọn port đang rảnh. Một worker gọi `accept()` hai lần, đóng socket của client thứ nhất rồi tiếp tục accept client thứ hai. Cuối cùng main kiểm tra trạng thái listener. Cả client và server đều có timeout để tránh demo chờ vô hạn.

Tạo tệp **`TcpTwoClientsDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.EOFException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class TcpTwoClientsDemo {
    public static void main(String[] args) throws Exception {
        ServerSocket listener = new ServerSocket();
        ExecutorService workers = Executors.newSingleThreadExecutor();
        try (listener) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0), 16);
            listener.setSoTimeout(5_000);

            Future<Integer> server = workers.submit(() -> {
                int handled = 0;
                for (int i = 0; i < 2; i++) {
                    try (Socket accepted = listener.accept()) {
                        accepted.setSoTimeout(5_000);
                        BufferedReader in = new BufferedReader(
                                new InputStreamReader(
                                        accepted.getInputStream(),
                                        StandardCharsets.UTF_8));
                        BufferedWriter out = new BufferedWriter(
                                new OutputStreamWriter(
                                        accepted.getOutputStream(),
                                        StandardCharsets.UTF_8));
                        String request = in.readLine();
                        if (request == null) {
                            throw new EOFException("Missing request");
                        }
                        out.write("ACK:" + request);
                        out.newLine();
                        out.flush();
                        handled++;
                    }
                }
                return handled;
            });

            for (String request : List.of("one", "two")) {
                try (Socket client = new Socket()) {
                    client.connect(new InetSocketAddress(
                            InetAddress.getLoopbackAddress(),
                            listener.getLocalPort()), 2_000);
                    client.setSoTimeout(5_000);
                    BufferedWriter out = new BufferedWriter(
                            new OutputStreamWriter(client.getOutputStream(),
                                    StandardCharsets.UTF_8));
                    BufferedReader in = new BufferedReader(
                            new InputStreamReader(client.getInputStream(),
                                    StandardCharsets.UTF_8));
                    out.write(request);
                    out.newLine();
                    out.flush();
                    String reply = in.readLine();
                    if (reply == null) {
                        throw new EOFException("Missing reply");
                    }
                    System.out.println("Request " + request + " -> " + reply);
                }
            }
            System.out.println("Handled: " + server.get(5, TimeUnit.SECONDS));
            System.out.println("Listener still open: " + !listener.isClosed());
        } finally {
            workers.shutdownNow();
        }
        System.out.println("Listener closed: " + listener.isClosed());
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 TcpTwoClientsDemo.java
java TcpTwoClientsDemo
~~~

**Stdout đã kiểm chứng bằng OpenJDK 24:**

~~~text
Request one -> ACK:one
Request two -> ACK:two
Handled: 2
Listener still open: true
Listener closed: true
~~~

Diễn giải kết quả:

1. `listener.bind(..., 0)` tạo **một** endpoint server, `getLocalPort()` trả port đã cấp. Hai client đều kết nối đến đúng port này.
2. `workers.submit()` giúp server nhận kết nối trong một worker song song với main thread đóng vai client; đó là thiết kế demo, không có ý nghĩa thread pool tối ưu.
3. Mỗi `try (Socket accepted = listener.accept())` sở hữu **một** connection server-side. Kết thúc request `one` đóng accepted socket thứ nhất; listener vẫn đủ sống để nhận `two`.
4. `BufferedReader.readLine()` yêu cầu newline; client gửi `out.newLine()` và `flush()`. Khi server phản hồi, server cũng flush để client đọc được dòng.
5. `Future.get()` đợi xử lý đủ hai connection và giúp không in kết luận khi worker chưa kết thúc.
6. `Listener still open: true` xuất hiện **trước** khi kết thúc `try (listener)`. Sau khi ra khỏi scope, `Listener closed: true`.

Vì server xử lý đúng hai lượt, nó không phải dịch vụ phục vụ liên tục. Đối với server production, cần vòng lặp với điều kiện stop, giới hạn tải, theo dõi active sockets và xử lý lỗi đầy đủ.

## 8. Ví dụ 2 chạy được: đóng listener nhưng accepted connection còn sống

Chương trình thứ hai nhận một client, sau đó worker **đóng ngay listener**. Accepted socket vẫn đọc bốn byte `PING`, gửi `OK\n`, và client vẫn nhận response. Đây là phép thử trực tiếp tính độc lập của hai loại socket.

Tạo tệp **`CloseListenerDemo.java`**:

~~~java
import java.io.EOFException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CloseListenerDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket(
                0, 16, InetAddress.getLoopbackAddress())) {
            Future<Boolean> served = worker.submit(() -> {
                try (Socket accepted = listener.accept()) {
                    listener.close();
                    boolean connectionStillOpen = !accepted.isClosed();
                    accepted.setSoTimeout(5_000);
                    byte[] input = accepted.getInputStream().readNBytes(4);
                    if (input.length != 4) {
                        throw new EOFException("Need four bytes");
                    }
                    accepted.getOutputStream().write(
                            "OK\n".getBytes(StandardCharsets.US_ASCII));
                    accepted.getOutputStream().flush();
                    return connectionStillOpen;
                }
            });

            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress(
                        InetAddress.getLoopbackAddress(),
                        listener.getLocalPort()), 2_000);
                client.setSoTimeout(5_000);
                client.getOutputStream().write(
                        "PING".getBytes(StandardCharsets.US_ASCII));
                byte[] reply = client.getInputStream().readNBytes(3);
                System.out.print("Reply: " +
                        new String(reply, StandardCharsets.US_ASCII));
            }
            System.out.println("Listener closed: " + listener.isClosed());
            System.out.println("Accepted was open: " +
                    served.get(5, TimeUnit.SECONDS));
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CloseListenerDemo.java
java CloseListenerDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
Reply: OK
Listener closed: true
Accepted was open: true
~~~

`listener.close()` làm endpoint lắng nghe không nhận client mới. Nhưng `accepted.isClosed()` vẫn `false` ngay sau thao tác đóng listener; stream của accepted socket vẫn giao tiếp với client. Client nhận `OK`, rồi handler thoát khỏi `try (accepted)` để đóng connection. Bởi vậy, **không được hiểu listener đã đóng là mọi client cũ đã ngừng làm việc**.

## 9. Thiết kế dừng server theo hai vòng đời

Một server dừng có kiểm soát nên tách **ngừng nhận client mới** khỏi **giải phóng các connection đang hoạt động**:

~~~text
RUNNING
  |
  v
STOP_ACCEPTING
  - đặt trạng thái stop
  - listener.close() để giải phóng accept() đang blocking
  - không chuyển thêm accepted socket cho worker
  |
  v
DRAINING
  - để handler đã chạy hoàn tất theo thời hạn
  - ngừng nhận task mới vào executor
  - chờ có deadline, không chờ vô hạn
  |
  v
FORCE_CLOSE (nếu vượt deadline)
  - đóng accepted sockets còn active do server sở hữu
  - yêu cầu cancel/interrupt worker và quan sát lỗi
  |
  v
STOPPED
  - đóng tài nguyên còn sở hữu
  - xác nhận executor đã shutdown
~~~

Những điểm quan trọng:

- Đóng `ServerSocket` thường khiến thread đang chờ `accept()` nhận `SocketException`. Nếu việc đóng là **chủ động shutdown**, đây là tín hiệu dự kiến, không nhất thiết là lỗi nghiêm trọng cần retry.
- Đóng listener **không tự động** gọi `close()` cho các accepted sockets trước đó. Muốn force close phải quản lý từng connection, thường qua registry thread-safe gắn với ownership handler.
- `ExecutorService.shutdown()` ngừng nhận task mới nhưng không tự đóng accepted sockets. `shutdownNow()` yêu cầu interrupt; không được xem đó là đảm bảo giải phóng mọi blocking socket I/O.
- Khi cần dừng cưỡng bức, **đóng accepted socket do ứng dụng sở hữu** thường là bước cần thiết để giải phóng thread bị chặn ở I/O; kết hợp timeout và deadline.
- Một server có nhiều request trong cùng một connection có thể cần chính sách ngừng nhận **request** mới và drain request đang chạy, ngoài việc đóng listener.

Ví dụ quản lý registry ở mức ý tưởng (không phải chương trình độc lập):

~~~java
activeConnections.add(accepted);
try {
    executor.execute(() -> {
        try (accepted) {
            handleClient(accepted);
        } catch (IOException e) {
            reportError(e);
        } finally {
            activeConnections.remove(accepted);
        }
    });
} catch (RejectedExecutionException e) {
    activeConnections.remove(accepted);
    try {
        accepted.close();
    } catch (IOException closeError) {
        e.addSuppressed(closeError);
    }
    throw e;
}
~~~

`activeConnections` phải thread-safe và được đồng bộ với trạng thái shutdown để không có race giữa đăng ký, submit và force-close. Các tên `accepted`, `executor`, `handleClient`, `reportError` do ứng dụng cung cấp. `handleClient` ném `IOException`; runtime exception còn cần chính sách xử lý/log phù hợp. Đặt quy tắc ownership rõ trước khi chọn collection hoặc framework.

## 10. Timeout, blocking và phân loại lỗi

Listener và accepted socket có **timeout độc lập**:

~~~java
listener.setSoTimeout(3_000);
Socket accepted = listener.accept(); // timeout cho accept()
~~~

Nếu không có connection đến trong thời hạn, `accept()` ném `SocketTimeoutException`; listener không tự bị đóng chỉ vì timeout.

~~~java
try (Socket accepted = listener.accept()) {
    accepted.setSoTimeout(3_000);
    int firstByte = accepted.getInputStream().read(); // timeout cho read()
}
~~~

`Socket.setSoTimeout()` giới hạn blocking **read trên connection này**, không tự áp dụng cho `ServerSocket.accept()` hoặc cho mọi accepted socket khác. Nó không là timeout tổng giao dịch hoặc write timeout.

| Vấn đề | Nơi phát sinh thường gặp | Phản ứng |
| --- | --- | --- |
| `BindException` | `bind()`/constructor listener | Cấu hình endpoint lỗi hoặc port đang dùng; chưa thể phục vụ |
| `SocketTimeoutException` khi accept | `ServerSocket.accept()` | Chưa có client trong thời hạn; có thể kiểm tra trạng thái và accept tiếp |
| `SocketTimeoutException` khi đọc | `Socket.getInputStream().read()` | Một client chậm, khung dữ liệu chưa đủ; xử lý theo protocol |
| `SocketException` khi listener đóng | `accept()` đang chờ | Nếu planned shutdown, dừng vòng lặp; nếu không, chẩn đoán lỗi |
| `IOException` lúc đọc/ghi client | Handler của accepted socket | Xử lý/đóng connection đó, không mặc định dừng cả listener |
| `RejectedExecutionException` | Executor không nhận thêm task | Caller đóng accepted socket chưa giao được |
| `ExecutionException` | `Future.get()` | Xem cause để biết worker lỗi gì |

Một client bị lỗi framing không đồng nghĩa listener đã bị lỗi. Ngược lại, nếu không bind được server socket thì không có endpoint hợp lệ để accept. Logging và recovery nên tách lỗi **listener-level** khỏi lỗi **connection-level**.

TCP là byte stream: `read()` có thể trả ít byte hơn mong muốn. `readLine()` đợi newline hoặc EOF; `InputStream.available()` không xác định được đã nhận trọn message. Mỗi handler cần framing (line delimiter, length prefix...), giới hạn frame, timeout và kiểm soát tài nguyên; không biến `accept()` thành cách xác định ranh giới message.

## 11. Các lỗi phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng listener để đọc body từ client | `ServerSocket` không chứa stream riêng của client | Dùng `Socket` trả về từ `accept()` |
| Tạo `new ServerSocket(samePort)` cho mỗi client | Xung đột bind, cấu trúc sai | Bind listener một lần và accept nhiều lần |
| Cho rằng `accept()` “biến” listener thành client socket | Mất ranh giới lifecycle | Giữ listener; accepted socket là đối tượng khác |
| Đóng accepted A rồi nghĩ B/listener cũng đóng | Connection B vẫn tồn tại | Đóng từng accepted socket theo handler |
| Đóng listener rồi nghĩ tất cả accepted sockets đã đóng | Worker cũ còn I/O và tài nguyên | Drain/close accepted sockets riêng |
| `try (accepted)` ở caller khi giao async | Đóng socket trước khi task chạy | Handler nhận ownership và tự close |
| Executor từ chối nhưng không close accepted | Rò file descriptor/kết nối | Caller close khi giao task thất bại |
| Dùng `accepted.getPort()` làm cổng server | Nhầm remote port | `getLocalPort()` trên listener hoặc accepted |
| Nghĩ backlog là tổng số client tối đa | Quyết định tải sai | Phân biệt backlog, active connections và worker pool |
| Set timeout listener rồi nghĩ read của client có timeout | Handler có thể đợi dữ liệu vô hạn | Set `SO_TIMEOUT` trên từng accepted `Socket` |
| Khi planned stop, retry `accept()` mãi dù listener đóng | Vòng lặp lỗi nóng | Thoát theo trạng thái shutdown |
| Chỉ `shutdownNow()` mà không đóng socket | Worker có thể vẫn kẹt I/O | Dùng deadline và close socket được sở hữu |
| Mỗi client chậm khiến server ngừng nhận client khác | Xử lý blocking ngay trên accept thread | Worker/concurrency phù hợp |
| Coi `close()` là xác nhận nghiệp vụ thành công | Có thể mất phản hồi/ACK | Giao thức xác nhận ở tầng ứng dụng |

## 12. Checklist thực hành

- [ ] Tôi phân biệt rõ `ServerSocket` listener và `Socket` cho từng client.
- [ ] Listener được bind một lần vào đúng local address/port.
- [ ] `accept()` chạy trong vòng lặp có cơ chế stop rõ.
- [ ] Mỗi accepted socket có một owner chịu trách nhiệm đóng.
- [ ] Nếu giao task async, caller không đóng socket trước khi worker kết thúc.
- [ ] Nếu executor từ chối, socket chưa giao được được cleanup.
- [ ] Có timeout và framing cho từng connection, không chỉ timeout listener.
- [ ] Mức đồng thời, queue và active connection có giới hạn.
- [ ] Shutdown có giai đoạn ngừng accept và giai đoạn xử lý/đóng các kết nối cũ.
- [ ] Lỗi của một connection không tự động trở thành lỗi của toàn listener.
- [ ] Chỉ số và log phân biệt accepted/active/error trên đúng tầng.
- [ ] Tôi không ngộ nhận `close()` hoặc TCP FIN là xác nhận request thành công.

## 13. Bài tập có đáp án

**Bài 1.** Server gọi `accept()` thành công hai lần, nhận A và B. Có bao nhiêu loại/tài nguyên socket được nêu ở phía server?

**Đáp án:** Một `ServerSocket` listener và hai `Socket` cho A/B. Hai accepted sockets là hai kết nối độc lập, có thể cùng port local của listener.

**Bài 2.** Đóng accepted A có tự làm listener ngừng nhận kết nối mới không? B có bị đóng theo không?

**Đáp án:** Không. `acceptedA.close()` chỉ đóng connection A. Nếu listener còn mở, nó có thể accept thêm client; B không bị đóng tự động.

**Bài 3.** Khi server đóng listener sau khi đã accept A, handler A có tiếp tục gửi reply không?

**Đáp án:** Có thể. Accepted socket A vẫn là connection hợp lệ và độc lập; listener ngừng nhận client mới. Muốn chặn A phải đóng A hoặc yêu cầu handler hủy.

**Bài 4.** Vì sao đoạn sau sai khi xử lý bất đồng bộ?

~~~java
try (Socket s = listener.accept()) {
    executor.submit(() -> handleClient(s));
}
~~~

**Đáp án:** Socket `s` bị đóng ngay khi thoát try, trong khi task chưa chắc đã chạy xong. Đưa `try (s)` vào worker; nếu submit bị từ chối, caller chịu trách nhiệm close.

**Bài 5.** Listener bind `127.0.0.1:7000` với backlog 32; accepted socket có remote port 50123. Client tiếp theo nên connect port nào? Backlog 32 có phải số connection xử lý tối đa suốt đời server?

**Đáp án:** Connect port 7000. Port 50123 là port phía client đang kết nối. Backlog là hàng đợi chờ accept theo OS, không giới hạn tổng số client đã phục vụ.

**Bài 6.** Gọi `listener.setSoTimeout(1000)` rồi `accept()` timeout. Listener có tự đóng không? Accepted sockets tự có read timeout 1000 ms không?

**Đáp án:** Không. Timeout của listener áp dụng cho `accept()`, còn `setSoTimeout()` của accepted `Socket` áp dụng cho blocking read của connection đó.

**Bài 7.** Khi shutdown, server có 100 accepted sockets đang chạy. Chỉ đóng listener đã đủ giải phóng tất cả connection chưa?

**Đáp án:** Chưa. Đóng listener ngừng nhận mới; server còn cần drain hoặc force-close accepted sockets theo deadline và shutdown worker/executor.

## 14. Tài liệu chuẩn

- [JDK 17 — `java.net.ServerSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): bind, accept, close, timeout, local endpoint.
- [JDK 17 — `java.net.Socket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): input/output streams, local/remote endpoints, close và half-close.
- [JDK 17 — `java.net.InetSocketAddress`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetSocketAddress.html): biểu diễn IP/hostname và port.
- [JDK 17 — `java.net.SocketTimeoutException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketTimeoutException.html): timeout trong socket I/O.
- [JDK 17 — `java.util.concurrent.ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit, shutdown và xử lý worker.
- [Oracle Java Tutorials — All About Sockets](https://docs.oracle.com/javase/tutorial/networking/sockets/): mô hình client/server TCP cơ bản.

**Ghi nhớ:** `ServerSocket` đón kết nối; `accept()` tạo ra `Socket` dùng để phục vụ riêng mỗi client. Hai loại socket có **ownership, dữ liệu, timeout và vòng đời đóng riêng biệt**. Khi tách đúng những phạm vi đó, server có thể nhận nhiều client, chịu lỗi từng connection và shutdown có kiểm soát.
