# Blocking receive và phối hợp luồng xử lý UDP trong Java 15+

## 1. Mục tiêu bài học

Trong ứng dụng sử dụng **UDP**, một luồng có thể đợi datagram từ mạng bằng `DatagramSocket.receive(DatagramPacket)`. Lời gọi này thường **blocking**: nó chỉ hoàn tất khi một datagram được nhận, khi hết thời gian chờ đã cấu hình, khi socket đóng hoặc khi có lỗi I/O. Trong lúc đợi, luồng nhận không nên phải liên tục kiểm tra (*busy polling*) hay giữ trách nhiệm xử lý nghiệp vụ nặng.

Bài học nằm trong nhóm **Điều khiển UDP** của module **Java 15**. JEP 373 của Java 15 **tái triển khai phần bên trong** của API `DatagramSocket` và `MulticastSocket` bằng cơ chế dễ bảo trì hơn; **không phải** Java 15 mới giới thiệu `DatagramSocket.receive`, `setSoTimeout` hay `close`. Các API này vẫn được hỗ trợ trên JDK hiện hành.

Chúng ta sẽ xây mô hình **một receiver thread + hàng đợi có giới hạn + hai worker threads**, kiểm thử trên loopback bằng Java 17+, đồng thời phân biệt rõ:

1. Khi nào `receive()` chặn và cách áp dụng `SO_TIMEOUT`.
2. Cách chuyển datagram vừa nhận sang worker mà **không chia sẻ sai buffer đang thay đổi**.
3. Cách `close()` đánh thức thread bị chặn trong `receive()` và cách phối hợp dừng các worker.
4. Hành vi liên quan đến lỗi, packet bị cắt, queue đầy và tính không bảo đảm của UDP.
5. Khi nào cần `DatagramChannel` + `Selector` thay vì một luồng blocking trên một socket.

**Giới hạn quan trọng:** UDP không bảo đảm gói tin đến, không bảo đảm thứ tự và có thể xảy ra mất/trùng gói. Chương trình local loopback ở mục 7 kiểm tra **một tình huống thử nghiệm xác định**, không chứng minh mọi mạng đều nhận đủ ba gói.

## 2. Blocking receive thực sự làm gì?

Với `DatagramSocket` đang mở và đã bind:

~~~java
byte[] buffer = new byte[2048];
DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
socket.receive(packet);
~~~

Đây là **đoạn minh họa**, trong đó `socket` đã là một `DatagramSocket` hợp lệ. `receive(packet)`:

- Thường **đợi** đến khi một UDP datagram được nhận trên socket đó.
- Ghi dữ liệu vào `packet.getData()` từ vị trí `getOffset()`; `getLength()` cho biết **số byte thực nhận**; `getSocketAddress()` cung cấp địa chỉ nguồn.
- Xử lý **một datagram tại một lần gọi**, không phải một luồng byte liên tục như TCP. Datagram nhận được có thể đã bị **cắt phần vượt quá buffer** và phần dư bị bỏ, không có cách “đọc tiếp nửa còn lại” bằng một `receive()` mới.
- Không tự giải mã UTF-8, không tự xác minh nguồn gửi và không tự tạo cơ chế xác nhận/khôi phục mất gói.

`DatagramPacket` **là một đối tượng có trạng thái**. Khi nhận, trường độ dài được cập nhật; nếu tái sử dụng một `DatagramPacket` sau khi nhận một gói ngắn, cần đặt lại độ dài buffer cho lần sau bằng `packet.setLength(buffer.length)` (hoặc tạo packet mới). Nếu không, lần nhận tiếp theo có thể bị giới hạn sai theo độ dài cũ.

Ví dụ giải mã đúng **phần bytes nhận được**, không giải mã toàn bộ dung lượng buffer:

~~~java
String text = new String(
        packet.getData(),
        packet.getOffset(),
        packet.getLength(),
        StandardCharsets.UTF_8);
~~~

Nếu `buffer` có 2048 phần tử và datagram chỉ dài 4 byte, xử lý cả 2048 byte sẽ làm lẫn phần dư hoặc các byte bằng zero. `getLength()` là độ dài dữ liệu nhận được **trong packet**, không phải dung lượng buffer và cũng không phải số ký tự văn bản.

## 3. Ba cách thoát khỏi lời gọi receive đang chặn

### 3.1. Có datagram đến

Trường hợp bình thường: `receive(packet)` trả về và luồng tiếp tục. Gói có địa chỉ/port nguồn; nếu đang dùng socket không kết nối (*unconnected*) thì receiver có thể nhận từ nhiều peer khác nhau. `DatagramSocket.connect(remote)` trên UDP chỉ liên kết địa chỉ peer mặc định và lọc các gói theo địa chỉ từ xa phù hợp; **nó không tạo kết nối đáng tin cậy như TCP**.

### 3.2. Hết thời gian chờ SO_TIMEOUT

~~~java
socket.setSoTimeout(500); // 500 milliseconds; cấu hình trước receive()
try {
    socket.receive(packet);
    // Đã có một datagram.
} catch (SocketTimeoutException timeout) {
    // Không nhận được datagram trong khoảng chờ; socket vẫn còn dùng được.
}
~~~

Đây là đoạn minh họa. Theo Javadoc, `setSoTimeout(int)` quy định thời gian chờ của `receive` tính bằng **millisecond**:

- Giá trị **lớn hơn 0**: `receive` có thể ném `SocketTimeoutException` khi hết thời gian chờ; **socket không tự đóng** và có thể gọi `receive` tiếp.
- Giá trị **0**: timeout bị tắt, tức `receive` có thể chờ **không giới hạn**.
- Giá trị **âm**: không hợp lệ, ném `IllegalArgumentException`.
- Timeout phải được thiết lập **trước khi bắt đầu** thao tác receive blocking mà ta muốn áp dụng.

Timeout **không chứng minh peer offline** và cũng không có nghĩa một datagram sẽ đến đúng sau khoảng chờ. Nó chỉ giới hạn một lần đợi cụ thể. Không dùng vòng lặp timeout vài millisecond để mô phỏng non-blocking nếu ứng dụng thực chất cần `DatagramChannel` + `Selector`.

### 3.3. Socket đóng khi thread đang nhận

~~~java
socket.close();
~~~

Khi một thread đang bị chặn trong `DatagramSocket.receive(packet)` và thread khác gọi `close()`, theo API thread đang nhận sẽ bị đánh thức và **ném `SocketException`**. Đây là cơ chế dừng receiver **đáng tin cậy trên các `DatagramSocket` thông thường**; trong catch, cần phân biệt **dừng chủ động** với **lỗi mạng bất ngờ**.

Ví dụ một vòng lặp:

~~~java
try {
    while (running.get()) {
        DatagramPacket incoming = new DatagramPacket(new byte[2048], 2048);
        socket.receive(incoming);
        process(incoming); // chỉ minh họa; xem thiết kế queue ở mục 5.
    }
} catch (SocketException ex) {
    if (!running.get() && socket.isClosed()) {
        // Socket đóng theo kế hoạch dừng.
    } else {
        // Lỗi socket không mong đợi: báo cáo/giám sát.
    }
}
~~~

Mã này chỉ là **đoạn minh họa**: `running`, `socket`, `process` được định nghĩa ở chương trình xung quanh. Đừng bắt mọi `SocketException` rồi âm thầm xem là dừng bình thường.

**Không nên dựa vào `Thread.interrupt()` một cách chung chung để đánh thức mọi platform thread đang `receive` trên `DatagramSocket` thông thường.** Quy tắc ngắt phụ thuộc loại socket/channel và ngữ cảnh runtime. `DatagramSocket` gắn với `DatagramChannel` có hành vi interrupt thông qua channel (có thể ném `ClosedByInterruptException`); trên JDK hiện đại virtual thread cũng có quy tắc riêng. Nếu cần dừng một `DatagramSocket` theo cách rõ ràng và dễ kiểm thử, dùng **`close`** và phối hợp với trạng thái dừng.

## 4. Vì sao không xử lý nghiệp vụ nặng ngay trong receiver?

Giả sử `receive` vừa nhận một datagram, nhưng receiver lập tức:

- giải mã JSON lớn;
- gọi cơ sở dữ liệu hoặc API bên ngoài;
- ghi file hoặc chạy tác vụ CPU kéo dài;
- chờ một khóa đồng bộ đang bị tranh chấp.

Trong thời gian đó receiver **không gọi `receive` tiếp**. Các datagram có thể tích tụ trong buffer nhận của hệ điều hành; khi buffer đầy, gói mới có thể bị **drop**. UDP không có cơ chế đảm bảo gửi lại ở tầng transport để khôi phục những gói đó.

Mô hình cơ bản nên là:

~~~text
                    UDP datagrams trên mạng
                              |
                              v
                 DatagramSocket.receive() 
                       1 receiver thread
                              |
                  copy đúng bytes & metadata
                              |
                              v
                    BlockingQueue hữu hạn
                      /             \
                     v               v
                  Worker A        Worker B
                     |               |
                 decode/validate/process
                              |
                   giám sát lỗi + thống kê

Shutdown: running=false -> socket.close()
         -> receiver rời receive() -> workers hoàn tất/dừng
~~~

**Một receiver đọc socket** giúp tránh chia trách nhiệm nhận gói cho nhiều luồng không cần thiết. Có thể có nhiều worker xử lý song song, nhưng khi đó **thứ tự hoàn thành các công việc có thể khác thứ tự nhận datagram**. Nếu mỗi peer cần giữ thứ tự hoặc trạng thái tuần tự, phải định tuyến theo peer, sequence number hoặc áp dụng cơ chế đồng bộ/partitioning phù hợp.

### Kiến trúc queue phải có giới hạn

`ArrayBlockingQueue` là một `BlockingQueue` có kích thước tối đa cố định, giúp giới hạn dữ liệu đang chờ xử lý ở tầng ứng dụng. Dùng:

~~~java
BlockingQueue<Received> jobs = new ArrayBlockingQueue<>(256);
~~~

Với `queue.put(job)`, nếu hàng đợi đầy thì **receiver sẽ chặn ở `put`**, không đọc UDP mới, và các gói có thể bị drop ở tầng hệ điều hành. Cần lựa chọn một chính sách **rõ ràng** cho tải cao:

- `offer(job)` để từ chối/đếm số gói quá tải thay vì chờ vô hạn;
- `offer(job, timeout, unit)` để đợi có giới hạn;
- tăng worker hoặc xử lý nhẹ hơn, nhưng vẫn giới hạn queue/tài nguyên;
- phân vùng theo khóa nghiệp vụ khi cần giữ thứ tự.

Đừng mặc định dùng queue vô hạn để tránh drop: backlog có thể tăng tới mức hết bộ nhớ. Cũng đừng mô tả `ArrayBlockingQueue` là cơ chế làm cho UDP trở nên đáng tin cậy — queue chỉ điều tiết **sau khi gói đã được JVM nhận**.

## 5. Sở hữu buffer và phối hợp dữ liệu giữa các thread

### Copy dữ liệu trước khi giao cho worker

`DatagramPacket.getData()` trả **tham chiếu đến mảng byte gốc**, không tự sao chép. Nếu receiver tái sử dụng mảng đó trong `receive` kế tiếp, worker có thể đọc phải dữ liệu đã bị ghi đè. Thiết kế an toàn:

~~~java
DatagramPacket packet = new DatagramPacket(new byte[2048], 2048);
socket.receive(packet);

byte[] ownedBytes = Arrays.copyOfRange(
        packet.getData(),
        packet.getOffset(),
        packet.getOffset() + packet.getLength());

SocketAddress from = packet.getSocketAddress();
queue.put(new Received(ownedBytes, from));
~~~

Đây là đoạn minh họa; `queue` và `Received` được định nghĩa ở mục 7. Worker nhận **mảng bytes riêng** cùng **metadata nguồn**. Chỉ worker được quyền biến đổi dữ liệu nó sở hữu; nếu chia chung dữ liệu, cần quy tắc đồng bộ riêng.

Có thể dùng `record Received(byte[] bytes, SocketAddress source)` để gói dữ liệu/nguồn, nhưng nhớ rằng `record` **không tự sao chép nội dung mảng** và `byte[]` bên trong vẫn có thể thay đổi. Độ an toàn ở ví dụ đến từ việc receiver **đã copy bytes** trước khi đưa vào queue và không sửa mảng đó nữa.

### Phối hợp dừng receiver và worker

Một trình tự dừng dễ hiểu:

1. Đặt trạng thái `running=false` (ví dụ `AtomicBoolean` dùng chung).
2. Gọi `socket.close()` để giải phóng thread đang blocking trong `receive`.
3. `receiver.join(...)` để xác nhận thread nhận đã kết thúc.
4. Cho worker xử lý nốt tác vụ đã nằm trong queue (hoặc có chính sách bỏ hàng đợi rõ ràng).
5. `ExecutorService.shutdown()` và `awaitTermination(...)`; nếu hết hạn, ứng dụng quyết định có `shutdownNow()` và ghi nhận phần việc bị bỏ hay không.

**Điểm dễ bị bỏ sót:** `socket.close()` **chỉ trực tiếp giải phóng receive đang chặn**, không tự đánh thức receiver nếu nó đang chặn ở `queue.put(job)` vì queue đầy. Với tải lớn cần thiết kế dừng thêm cho trạng thái này, ví dụ dùng `offer` có timeout, `interrupt` ở thao tác queue hoặc một cơ chế báo dừng thích hợp. Ví dụ ở mục 7 chỉ gửi ba datagram vào queue chứa tám phần tử nên không rơi vào trường hợp queue đầy.

`ExecutorService.shutdown()` không hủy mọi task đang chạy; nó ngừng nhận task mới. `shutdownNow()` yêu cầu dừng bằng interrupt nhưng tác vụ phải hợp tác để dừng. Không coi việc gọi shutdown là bằng chứng các worker đã rời tác vụ; cần `awaitTermination` hoặc theo dõi các `Future`.

## 6. Các phương án phối hợp: blocking socket hay NIO?

| Phương án | Cơ chế nhận | Khi nào nên dùng |
| --- | --- | --- |
| `DatagramSocket.receive` + một thread | Blocking; `setSoTimeout` hoặc `close` để kiểm soát chờ/dừng | Ứng dụng có ít socket UDP, luồng đơn giản, dễ đọc và dễ kiểm thử. |
| `DatagramSocket.receive` + queue + worker pool | Thread nhận chuyên I/O, worker xử lý riêng; queue giới hạn backlog | Khi xử lý mỗi datagram có chi phí và cần tránh làm chậm lượt nhận tiếp. |
| `DatagramChannel` blocking | `receive(ByteBuffer)` chờ datagram, dùng ByteBuffer | Khi muốn API NIO, kết hợp với các thao tác channel khác. |
| `DatagramChannel.configureBlocking(false)` + `Selector` | Channel ở chế độ non-blocking, chờ sự kiện `OP_READ` | Khi quản lý nhiều socket/kênh và cần event loop. |

Với `DatagramChannel` non-blocking, `receive(ByteBuffer)` có thể **trả `null`** nếu chưa có datagram. Trong chế độ blocking, nó đợi datagram. Ngắt thread đang đọc channel có thể **đóng channel** và gây `ClosedByInterruptException`; đóng channel từ thread khác trong lúc đang đọc có thể gây `AsynchronousCloseException`. Đây là các ngoại lệ của **channel**, không phải lời hứa rằng `Thread.interrupt()` trên mọi socket UDP sẽ có cùng kết quả.

Một `DatagramSocket` được lấy từ `DatagramChannel.socket()` còn có liên hệ với mode của channel: nếu channel ở chế độ non-blocking mà gọi `DatagramSocket.receive`, có thể gặp `IllegalBlockingModeException`. Không vừa dùng vòng lặp `Socket.receive` vừa tùy tiện `configureBlocking(false)` trên channel liên kết.

**Java 15 / JEP 373:** việc thay lớp triển khai `DatagramSocket` và `MulticastSocket` phía trong không bắt ứng dụng cũ đổi toàn bộ sang `DatagramChannel`. Hành vi API được giữ tương thích; lựa chọn blocking hoặc NIO là **quyết định kiến trúc hiện hành**, không phải yêu cầu di trú bắt buộc vì JEP 373.

## 7. Chương trình hoàn chỉnh: receiver + queue + hai worker, có shutdown

Lưu file **`UdpReceiveCoordinationDemo.java`** bằng UTF-8. Ví dụ chỉ dùng **loopback trên máy hiện tại**, cổng UDP tự cấp (`0` khi bind), một thread nhận và hai worker. Dữ liệu thử gồm `"ping"`, `"Tiếng Việt"` và `"end"`; chương trình **không in cổng động hoặc tên luồng** để stdout ổn định.

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.io.IOException;
import java.util.Arrays;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class UdpReceiveCoordinationDemo {
    private record Received(byte[] bytes, SocketAddress source) {}
    private static int passed;

    private static void check(String label, boolean condition) {
        if (!condition) throw new AssertionError(label);
        passed++;
        System.out.println(label + "=PASS");
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (DatagramSocket idle =
                new DatagramSocket(new InetSocketAddress(loopback, 0))) {
            idle.setSoTimeout(150);
            boolean timeout = false;
            try {
                idle.receive(new DatagramPacket(new byte[32], 32));
            } catch (SocketTimeoutException expected) {
                timeout = true;
            }
            check("timeoutKeepsSocketOpen", timeout && !idle.isClosed());
        }

        BlockingQueue<Received> queue = new ArrayBlockingQueue<>(8);
        Set<String> messages = ConcurrentHashMap.newKeySet();
        AtomicReference<Throwable> error = new AtomicReference<>();
        AtomicInteger receivedCount = new AtomicInteger();
        AtomicBoolean running = new AtomicBoolean(true);
        AtomicBoolean closeUnblocked = new AtomicBoolean();
        AtomicBoolean allLoopback = new AtomicBoolean(true);
        CountDownLatch receiverReady = new CountDownLatch(1);
        CountDownLatch firstReceived = new CountDownLatch(1);
        CountDownLatch processed = new CountDownLatch(3);
        ExecutorService workers = Executors.newFixedThreadPool(2);

        for (int i = 0; i < 2; i++) {
            workers.submit(() -> {
                try {
                    while (running.get() || !queue.isEmpty()) {
                        Received job = queue.poll(100, TimeUnit.MILLISECONDS);
                        if (job == null) continue;
                        if (!(job.source() instanceof InetSocketAddress address)
                                || !address.getAddress().isLoopbackAddress()) {
                            allLoopback.set(false);
                        }
                        messages.add(new String(job.bytes(), StandardCharsets.UTF_8));
                        processed.countDown();
                    }
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    error.compareAndSet(null, interrupted);
                }
            });
        }

        DatagramSocket server =
                new DatagramSocket(new InetSocketAddress(loopback, 0));
        Thread receiver = new Thread(() -> {
            receiverReady.countDown();
            while (true) {
                DatagramPacket packet = new DatagramPacket(new byte[256], 256);
                try {
                    server.receive(packet);
                    firstReceived.countDown();
                    byte[] owned = Arrays.copyOfRange(packet.getData(),
                            packet.getOffset(), packet.getOffset() + packet.getLength());
                    queue.put(new Received(owned, packet.getSocketAddress()));
                    receivedCount.incrementAndGet();
                } catch (SocketException closedOrFailed) {
                    if (!running.get() && server.isClosed()) {
                        closeUnblocked.set(true);
                    } else {
                        error.compareAndSet(null, closedOrFailed);
                    }
                    break;
                } catch (IOException io) {
                    error.compareAndSet(null, io);
                    break;
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    error.compareAndSet(null, interrupted);
                    break;
                }
            }
        }, "udp-receiver");

        try {
            receiver.start();
            check("blockedBeforeSend",
                    receiverReady.await(2, TimeUnit.SECONDS)
                            && !firstReceived.await(150, TimeUnit.MILLISECONDS));

            String[] sent = {"ping", "Tiếng Việt", "end"};
            try (DatagramSocket sender =
                    new DatagramSocket(new InetSocketAddress(loopback, 0))) {
                for (String item : sent) {
                    byte[] bytes = item.getBytes(StandardCharsets.UTF_8);
                    sender.send(new DatagramPacket(
                            bytes, bytes.length, loopback, server.getLocalPort()));
                }
            }
            check("processedAll", processed.await(5, TimeUnit.SECONDS));
            check("payloadsCopied", messages.equals(Set.of("ping", "Tiếng Việt", "end")));
            check("sourceLoopback", allLoopback.get());
            check("receivedExactlyThree", receivedCount.get() == 3);
        } finally {
            running.set(false);
            server.close();
            receiver.join(2000);
            workers.shutdown();
            if (!workers.awaitTermination(3, TimeUnit.SECONDS)) {
                workers.shutdownNow();
            }
        }
        check("closeUnblocksReceive", closeUnblocked.get() && !receiver.isAlive());
        check("workersStopped", workers.isTerminated() && error.get() == null);
        System.out.println("TOTAL_PASS=" + passed);
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac --release 17 -encoding UTF-8 UdpReceiveCoordinationDemo.java
java UdpReceiveCoordinationDemo
~~~

**Stdout chuẩn cho lần chạy kiểm chứng trên loopback** (đã biên dịch và chạy với `javac --release 17`):

~~~text
timeoutKeepsSocketOpen=PASS
blockedBeforeSend=PASS
processedAll=PASS
payloadsCopied=PASS
sourceLoopback=PASS
receivedExactlyThree=PASS
closeUnblocksReceive=PASS
workersStopped=PASS
TOTAL_PASS=8
~~~

### Giải thích kết quả và điều kiện của test

- **`timeoutKeepsSocketOpen`:** một socket UDP riêng với timeout `150 ms` không nhận datagram và ném `SocketTimeoutException`, nhưng vẫn chưa bị đóng.
- **`blockedBeforeSend`:** receiver đã bắt đầu, sau khi chờ `150 ms` vẫn chưa có gói đầu tiên. Test dùng latch để quan sát **không nhận được gói trước khi gửi**, không kiểm tra trạng thái CPU hoặc trông đợi một `Thread.State` cụ thể.
- **`processedAll`:** ba công việc đã được worker hoàn tất trong thời gian thử nghiệm. Vì UDP không bảo đảm nhận đủ gói trong mọi môi trường, một hệ thống mạng bất thường có thể làm ca thử không đạt; test báo thất bại thay vì khẳng định UDP đáng tin.
- **`payloadsCopied`:** worker thấy đúng ba nội dung, bao gồm chữ tiếng Việt sau giải mã UTF-8; receiver đã copy đúng byte range trước khi giao cho worker.
- **`sourceLoopback`:** metadata nguồn cho biết datagram được gửi từ địa chỉ loopback trong test.
- **`receivedExactlyThree`:** receiver nhận chính xác ba datagram được gửi ở thử nghiệm này.
- **`closeUnblocksReceive`:** khi dừng, main đặt `running=false` rồi `server.close()`; thread receiver thoát `receive` qua `SocketException` và kết thúc.
- **`workersStopped`:** `ExecutorService` đã kết thúc, không có lỗi bất ngờ được ghi nhận qua `AtomicReference`.

**Giới hạn chương trình mẫu:** hàng đợi chỉ có ba job trên sức chứa tám phần tử, không kiểm tra trường hợp queue đầy. Thời gian chờ kiểm thử (`150 ms` / `5 s`) là giá trị thuận tiện cho môi trường local, **không phải SLA cho mạng thực**. Chương trình đặt ra thời hạn có thể làm test thất bại trên máy quá tải; điều đó nên được báo rõ thay vì suy ra rằng Java vi phạm hợp đồng API.

## 8. Vấn đề buffer, datagram dài và bảo toàn metadata

### 8.1. Packet bị cắt nếu buffer nhỏ

~~~java
byte[] receiveBuffer = new byte[4];
DatagramPacket packet = new DatagramPacket(receiveBuffer, receiveBuffer.length);
socket.receive(packet);
// Nếu datagram gốc dài hơn 4 byte, phần vượt quá bị cắt.
// Không thể tiếp tục nhận phần dư của cùng datagram ở lần receive kế tiếp.
~~~

Đây là đoạn minh họa; `socket` phải được cấp datagram tương ứng. Chú ý `getLength() == receiveBuffer.length` **không đủ chứng minh** gói đã bị cắt: cũng có thể gói nguyên bản dài đúng 4 byte. Nếu ứng dụng đòi xác minh kích thước đầy đủ, cần **định dạng giao thức có độ dài/kiểm tra hợp lệ** hoặc cấp buffer lớn đủ cho kích thước tối đa đã thống nhất. Đừng tin length do peer tự khai báo nếu chưa kiểm tra giới hạn.

### 8.2. Giữ nguồn gửi cùng bytes

`DatagramPacket.getSocketAddress()` cho địa chỉ/port nguồn trong lần nhận. Cần sao chép metadata này trước khi tái sử dụng packet và đưa cùng job tới worker. UDP source IP/port **không tự xác thực danh tính**: kẻ tấn công hoặc mạng trung gian có thể tạo/spoof datagram tùy môi trường. Các tác vụ quan trọng cần xác thực ở tầng ứng dụng (token/MAC/chữ ký/giao thức phù hợp) và hạn chế rate/size.

### 8.3. Không suy diễn thứ tự xử lý

Hai worker có thể lấy hai job và hoàn tất theo thứ tự khác nhau. Nếu giao thức cần thứ tự, định nghĩa **sequence number**, logic khử trùng lặp và xử lý out-of-order; nếu cần đảm bảo nhận đủ, phải bổ sung ACK/retry và tránh kiểm soát ùn tắc sai. Những tính năng đó **không có sẵn** chỉ bằng cách chuyển `receive` sang thread riêng.

## 9. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Receiver đứng đợi mãi | `receive` blocking và `SO_TIMEOUT=0`; chưa có datagram | Thiết lập timeout có chủ đích hoặc gọi `close` từ luồng điều phối khi dừng. |
| `SocketTimeoutException` | Hết thời gian chờ dương | Xử lý như không nhận được gói trong khoảng chờ, không mặc định socket hỏng. |
| `SocketException` khi dừng | Có thread khác gọi `socket.close()` | Nếu đúng trạng thái shutdown thì kết thúc bình thường; nếu không thì báo lỗi I/O. |
| Dừng bằng `running=false` nhưng receiver vẫn treo | Đang chặn trong `receive` và chỉ thay cờ không đánh thức I/O | Gọi `close` hoặc dùng cơ chế ngắt thích hợp của channel; kiểm tra join. |
| Đã close socket nhưng receiver vẫn không rời queue | Receiver có thể đang chặn ở `queue.put` vì queue đầy | Dùng `offer`, timeout, interrupt tác vụ queue hoặc thiết kế shutdown cho backpressure. |
| Worker đọc dữ liệu gói khác | Chia chung `DatagramPacket`/`byte[]` với receiver rồi ghi đè | `Arrays.copyOfRange` đúng `offset + length` trước khi publish sang queue. |
| Nội dung có ký tự rác/zero cuối | Giải mã toàn bộ buffer thay vì `getLength()` | Chỉ đọc `getOffset()` và `getLength()`; dùng UTF-8 minh bạch. |
| Gói dài nhận thiếu bytes | Buffer `DatagramPacket` nhỏ hơn datagram | Thỏa thuận giới hạn payload/buffer, kiểm tra length; không thể “đọc tiếp” nửa gói bị cắt. |
| Có nhiều worker nhưng kết quả không đúng thứ tự | Worker chạy song song; UDP cũng không bảo đảm thứ tự | Sequence number, phân vùng theo peer hoặc xử lý tuần tự nơi cần thiết. |
| Mất gói khi tải cao | Receiver bận, OS receive buffer/queue đầy, mạng drop | Tách I/O và work, đo drop/backlog, rate limiting, xử lý congestion và ứng dụng ACK nếu cần. |
| `IllegalBlockingModeException` | `DatagramSocket` gắn với channel đã đặt non-blocking | Chọn mô hình NIO/Selector nhất quán, không gọi Socket.receive trên channel non-blocking. |
| `PortUnreachableException` | Có thể xuất hiện ở connected socket với peer không truy cập được | Không được xem việc **không** có exception là bằng chứng peer chắc chắn reachable. |

## 10. Checklist thiết kế production

1. **Rõ vòng đời:** owner của `DatagramSocket` là ai, ai được phép đóng, và thread nào chịu trách nhiệm receiver?
2. **Rõ thời gian chờ:** chọn `setSoTimeout` có chủ đích; timeout không phải cơ chế cam kết delivery.
3. **Rõ giới hạn payload:** xác định kích thước tối đa của datagram ở tầng ứng dụng, tránh phụ thuộc vào fragment IP hoặc buffer mơ hồ.
4. **Rõ sở hữu dữ liệu:** copy bytes/metadata trước khi bàn giao sang worker; không chia một packet mutable cho nhiều tác vụ.
5. **Rõ chính sách quá tải:** bounded queue, số worker, giới hạn công việc và hành vi khi queue đầy; thống kê `offer` thất bại, backlog, latency.
6. **Rõ shutdown:** `running=false`, `socket.close()`, `join`, drain/stop worker, timeout dừng. Không để receiver mắc kẹt ở `queue.put`.
7. **Rõ xử lý ngoại lệ:** phân biệt `SocketTimeoutException`, đóng socket có kế hoạch, lỗi I/O và lỗi worker.
8. **Rõ thứ tự và độ tin cậy:** UDP có thể mất, lặp, đảo thứ tự. Nếu cần đảm bảo thứ tự hoặc delivery, thiết kế tầng giao thức phù hợp hoặc đánh giá transport khác.
9. **Rõ bảo mật:** không tin IP/port nguồn một cách tuyệt đối, xác minh thông điệp theo nghiệp vụ, chặn payload quá lớn và hạn chế DoS.
10. **Rõ kế hoạch kiểm thử:** test loopback, timeout, close, packet length, lỗi worker, queue full, tăng tải, và kiểm thử mạng thực với packet loss/reordering có kiểm soát.

## 11. Tài liệu chuẩn và API hiện hành

- [Java SE 26 — DatagramSocket](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/DatagramSocket.html): `receive(DatagramPacket)`, `setSoTimeout`, `close`, ngắt và ngoại lệ.
- [Java SE 26 — DatagramPacket](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/DatagramPacket.html): `getData`, `getOffset`, `getLength`, metadata nguồn, `setLength`.
- [Java SE 26 — DatagramChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/DatagramChannel.html): blocking/non-blocking, `receive(ByteBuffer)` và các ngoại lệ đóng/ngắt channel.
- [Java SE 26 — ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): `put`, `offer`, `poll` và hàng đợi có giới hạn.
- [Java SE 26 — ExecutorService](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `shutdownNow`, `awaitTermination`.
- [JEP 373 — Reimplement the Legacy Datagram Socket API](https://openjdk.org/jeps/373): tái triển khai phần bên trong API DatagramSocket/MulticastSocket ở Java 15, không thay đổi cách gọi chính của người dùng.
- [RFC 8085 — UDP Usage Guidelines](https://www.rfc-editor.org/rfc/rfc8085): lưu ý về UDP, kích thước datagram, điều tiết gửi và mất gói.

**Kết luận:** `DatagramSocket.receive` là thao tác UDP **blocking**; dùng `SO_TIMEOUT` hoặc `close` để kiểm soát chờ và dừng. Một thread chuyên nhận, **copy đúng byte[]**, đưa vào **queue hữu hạn** rồi phân phối cho worker giúp tách I/O khỏi nghiệp vụ. Tuy nhiên, backpressure, shutdown, giới hạn datagram và đảm bảo giao thức vẫn là trách nhiệm của ứng dụng, không tự có từ UDP hay Java 15.