# Mô hình xử lý tuần tự và ảnh hưởng của một máy khách chậm trong máy chủ TCP Java

Một TCP server đơn giản có thể sử dụng đúng **một luồng xử lý**: gọi `ServerSocket.accept()`, nhận một `Socket`, xử lý toàn bộ yêu cầu và phản hồi, đóng socket, rồi mới quay lại `accept()` cho máy khách tiếp theo. Cách viết này dễ hiểu và phù hợp cho bài tập khởi đầu, nhưng có một hệ quả lớn: **chỉ cần một client chậm, toàn bộ các client đứng sau có thể phải chờ**, ngay cả khi chúng đã kết nối TCP thành công và gửi đủ dữ liệu.

Đây là hiện tượng **head-of-line blocking ở tầng xử lý ứng dụng**: một tác vụ đứng đầu hàng giữ luồng xử lý, khiến những tác vụ đã sẵn sàng phía sau không được phục vụ. Bài học làm rõ luồng hoạt động, vai trò hàng đợi kết nối và buffer của hệ điều hành, cách tái hiện với Java 17+, phương án giới hạn thời gian/tài nguyên, cùng các lựa chọn tăng khả năng phục vụ đồng thời.

## 1. Server xử lý tuần tự hoạt động như thế nào?

Xem cấu trúc cơ bản của một TCP server:

~~~java
// Đoạn minh họa bên trong phương thức; listener đã được khởi tạo.
// handleClient(socket) đọc request và gửi response cho tới khi hoàn tất.
while (running) {
    Socket client = listener.accept();
    try (client) {
        handleClient(client);
    }
}
~~~

Đây là thứ tự **accept → handle → close → accept tiếp** trên cùng một luồng. Nếu `handleClient` bị chặn tại `InputStream.read()`, `BufferedReader.readLine()`, `OutputStream.write()` hoặc xử lý CPU lâu, vòng lặp không thể tiến tới lượt `accept()` kế tiếp.

~~~text
                 Một luồng xử lý ứng dụng
                             |
ServerSocket.accept() -------+-----> nhận client A
                             |
                       xử lý client A
                       readLine() chờ...
                             |
                   [A chưa hoàn thành]
                             |
                    không gọi accept()
                    không xử lý B, C...
                             |
                A xong / timeout / lỗi
                             |
                    đóng socket A
                             |
                    accept() client B
                             |
                       xử lý client B
~~~

Điều quan trọng là **TCP có thể thiết lập kết nối trong kernel trước khi ứng dụng Java gọi `accept()`**. Vì thế, client B có thể hoàn tất `connect()`, thậm chí gửi byte vào buffer TCP, trong khi server Java vẫn đang đọc từ A. Kết nối đã thiết lập ở mức TCP **không đồng nghĩa** yêu cầu của B đã được chương trình server đọc hoặc xử lý.

Một server tuần tự không nhất thiết “chỉ có một TCP connection tồn tại trên máy”. Nó có thể có một socket đang được ứng dụng xử lý và những kết nối khác đang chờ được chấp nhận; số lượng và hành vi phụ thuộc hệ điều hành, hàng đợi và tải.

## 2. Vì sao chỉ một client chậm đã ảnh hưởng cả hệ thống?

Một client được gọi là “chậm” khi nó khiến thời gian phục vụ kéo dài, có thể do mạng, hành vi ứng dụng hoặc một lỗi cố ý:

- **Gửi dữ liệu chậm hoặc không kết thúc thông điệp:** client gửi vài byte nhưng chưa gửi ký tự xuống dòng, độ dài payload đầy đủ hoặc dấu kết thúc do giao thức quy định. `readLine()`/`readNBytes(n)` có thể chờ.
- **Giữ kết nối nhưng không gửi gì:** server đang blocking `read()`, chờ một request chưa đến.
- **Đọc phản hồi rất chậm:** khi server ghi một phản hồi lớn, socket send buffer có thể đầy; `write()` có thể block vì peer không đọc đủ nhanh.
- **Gửi một yêu cầu đòi hỏi nhiều thời gian xử lý:** tính toán nặng, truy vấn cơ sở dữ liệu lâu hoặc gọi service khác bị treo. Dù mạng của client nhanh, luồng xử lý vẫn bị chiếm.
- **Cố ý nhỏ giọt byte:** mỗi khoảng thời gian gửi thêm một byte, giữ phiên tồn tại mà không tạo được request hoàn chỉnh. Đây là họ tình huống “slow client/slowloris”; không nên giả định cứ có read timeout là giải quyết hết.

Với cấu trúc tuần tự, mỗi trường hợp trên đều có thể giữ vị trí đầu và tạo thời gian chờ cho các yêu cầu khác.

### Ví dụ theo dòng thời gian

Giả sử server xử lý một client một lần:

| Thời điểm minh họa | Client A | Client B | Server |
| --- | --- | --- | --- |
| 0 ms | Kết nối, gửi `HEL` | Chưa đến | `accept(A)` và `readLine(A)` |
| 100 ms | Chưa gửi `\\n` | Kết nối, gửi trọn `PING\\n` | Vẫn đang chờ dòng đầy đủ từ A |
| 1.000 ms | Chưa gửi thêm | Chờ phản hồi | Chưa xử lý B dù request B đã đến buffer |
| 5.000 ms | Gửi phần còn lại và newline | Vẫn chờ | Đọc xong A, phản hồi A, rồi mới `accept(B)` |
| Sau đó | Hoàn tất | Nhận phản hồi | Xử lý B |

Các mốc thời gian chỉ là **tình huống minh họa**, không phải độ trễ bảo đảm. Điểm cốt lõi là **B không thể được xử lý bởi vòng lặp tuần tự trước khi xử lý A kết thúc**.

Nếu các client lần lượt chiếm thời gian phục vụ `T₁, T₂, ...`, thời gian chờ trước khi server bắt đầu xử lý client thứ `k` xấp xỉ tổng thời gian phục vụ của các client đứng trước trong hàng (cộng overhead), khi không có xử lý song song. Với một luồng, thông lượng phục vụ trong tải ổn định bị giới hạn bởi tốc độ hoàn thành một phiên tại một thời điểm; client chậm làm tăng cả thời gian chờ và độ biến động tail latency.

## 3. Vai trò của `ServerSocket.accept()` và hàng đợi backlog

Khi tạo listener:

~~~java
ServerSocket server = new ServerSocket(8080, 50);
~~~

Giá trị `50` là **gợi ý backlog** cho cơ chế hàng đợi kết nối, không phải số client mà Java có thể đồng thời xử lý, và cũng không phải cam kết sẽ cho phép đúng 50 kết nối trên mọi OS. Hệ điều hành có thể điều chỉnh/giới hạn theo chính sách của nó.

Có ba giai đoạn cần phân biệt:

1. **TCP handshake** được kernel xử lý. Khi thành công, client có thể thấy `Socket.connect()` hoàn tất.
2. **Ứng dụng server gọi `accept()`** để lấy một socket đã kết nối ra khỏi hàng đợi chờ accept.
3. **Ứng dụng thực sự đọc, xử lý và ghi phản hồi** trên socket đã nhận.

Trong mô hình tuần tự, bước 3 của A phải kết thúc trước khi vòng lặp thực hiện bước 2 cho B. Backlog chỉ giúp kernel giữ các kết nối chưa được ứng dụng accept trong giới hạn hạ tầng. **Tăng backlog không làm tăng số client được xử lý cùng lúc.**

Khi server bị giữ quá lâu và kết nối mới tiếp tục đến, hàng đợi có thể đầy. Client mới có thể gặp kết nối chậm, timeout hoặc bị từ chối tùy ngữ cảnh mạng/OS. Không khẳng định một ngoại lệ cụ thể luôn xảy ra, vì hoạt động TCP backlog và chính sách mạng có thể khác nhau.

## 4. Phân biệt “chậm trong accept”, “chậm trong read” và “chậm trong write”

| Điểm chặn | Vì sao chờ? | Hệ quả trong vòng lặp tuần tự | Giải pháp cần xem xét |
| --- | --- | --- | --- |
| `ServerSocket.accept()` | Không có kết nối mới để lấy | Luồng đang đợi client mới; chưa có client nào bị giữ bởi `handleClient` | Cấu hình accept timeout khi cần quản lý vòng đời |
| `Socket.getInputStream().read()` | Chưa có byte hoặc EOF | Client hiện tại chiếm luồng, client khác không được xử lý | Read timeout, framing, độ dài tối đa, deadline tổng |
| `BufferedReader.readLine()` | Chưa gặp newline hay EOF | Một dòng chưa kết thúc có thể giữ luồng | Quy định delimiter + giới hạn độ dài/thời gian |
| `InputStream.readNBytes(n)` | Chưa đủ n byte hoặc chưa EOF | Request thiếu byte khiến xử lý kéo dài | Giới hạn n, kiểm tra độ dài, timeout/deadline |
| `OutputStream.write(...)` | Send buffer có thể đầy, peer đọc chậm | Server bị chặn khi trả response; client sau đợi | Hạn chế response, I/O phù hợp và deadline ở cấp ứng dụng |
| Xử lý CPU/DB/API | Công việc lâu hoặc không hoàn tất | Dù socket nhanh vẫn tạo hàng chờ | Giới hạn thời gian xử lý, chuyển nhiệm vụ nặng, concurrency có kiểm soát |

**Không nhầm timeout:** `ServerSocket.setSoTimeout(ms)` giới hạn chờ ở `accept()`, còn `Socket.setSoTimeout(ms)` giới hạn **blocking read** trên socket. Cả hai không đặt deadline cho toàn bộ request và `Socket.setSoTimeout` không phải write timeout.

## 5. Thí nghiệm Java 17+: hai client, một luồng server

Đây là chương trình độc lập, chạy trên loopback, **không cần Internet hay DNS ngoài**. Một luồng duy nhất của server xử lý hai client theo thứ tự. Client chậm gửi `SLOW` nhưng không xuống dòng. Client nhanh kết nối sau, gửi `FAST\\n` đầy đủ, nhưng không thể nhận phản hồi cho tới khi client chậm hoàn tất.

Tạo tệp **`SequentialProof.java`**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SequentialProof {
    private static void handle(Socket socket, List<String> order)
            throws IOException {
        socket.setSoTimeout(5_000);
        BufferedReader in = new BufferedReader(new InputStreamReader(
                socket.getInputStream(), StandardCharsets.UTF_8));
        BufferedWriter out = new BufferedWriter(new OutputStreamWriter(
                socket.getOutputStream(), StandardCharsets.UTF_8));

        String line = in.readLine(); // Chờ newline hoặc EOF.
        if (line == null) {
            throw new EOFException("Empty request");
        }
        order.add(line);
        out.write("ACK:" + line);
        out.newLine();
        out.flush();
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        ExecutorService oneServerThread =
                Executors.newSingleThreadExecutor();

        try (ServerSocket server = new ServerSocket(0, 50, loopback)) {
            server.setSoTimeout(5_000);
            CountDownLatch firstAccepted = new CountDownLatch(1);

            Future<List<String>> order = oneServerThread.submit(() -> {
                List<String> result = new ArrayList<>();

                // Chấp nhận và xử lý client thứ nhất cho đến hết.
                try (Socket first = server.accept()) {
                    firstAccepted.countDown();
                    handle(first, result);
                }

                // Chỉ sau đó mới accept và xử lý client thứ hai.
                try (Socket second = server.accept()) {
                    handle(second, result);
                }
                return result;
            });

            try (Socket slow = new Socket(
                    loopback, server.getLocalPort())) {
                slow.setSoTimeout(5_000);

                if (!firstAccepted.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "First client was not accepted");
                }

                BufferedWriter slowOut = new BufferedWriter(
                        new OutputStreamWriter(
                                slow.getOutputStream(),
                                StandardCharsets.UTF_8));
                BufferedReader slowIn = new BufferedReader(
                        new InputStreamReader(
                                slow.getInputStream(),
                                StandardCharsets.UTF_8));

                // Cố ý gửi thiếu delimiter để server readLine() chờ.
                slowOut.write("SLOW");
                slowOut.flush();

                try (Socket fast = new Socket(
                        loopback, server.getLocalPort())) {
                    fast.setSoTimeout(250);

                    BufferedWriter fastOut = new BufferedWriter(
                            new OutputStreamWriter(
                                    fast.getOutputStream(),
                                    StandardCharsets.UTF_8));
                    BufferedReader fastIn = new BufferedReader(
                            new InputStreamReader(
                                    fast.getInputStream(),
                                    StandardCharsets.UTF_8));

                    fastOut.write("FAST");
                    fastOut.newLine();
                    fastOut.flush();

                    try {
                        System.out.println(
                                "fastBeforeSlowFinished="
                                        + fastIn.readLine());
                    } catch (SocketTimeoutException expected) {
                        System.out.println(
                                "fastBeforeSlowFinished=TIMEOUT");
                    }

                    // Mở khóa client chậm, cho server xử lý xong A.
                    slowOut.newLine();
                    slowOut.flush();

                    System.out.println(
                            "slowReply=" + slowIn.readLine());

                    // Timeout 250 ms không đóng connection fast.
                    fast.setSoTimeout(5_000);
                    System.out.println(
                            "fastReply=" + fastIn.readLine());

                    System.out.println(
                            "serverOrder="
                                    + order.get(5, TimeUnit.SECONDS));
                }
            }
        } finally {
            oneServerThread.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac SequentialProof.java
java SequentialProof
~~~

Đầu ra được kiểm tra trên Java (môi trường loopback bình thường):

~~~text
fastBeforeSlowFinished=TIMEOUT
slowReply=ACK:SLOW
fastReply=ACK:FAST
serverOrder=[SLOW, FAST]
~~~

**Ý nghĩa từng dòng:**

1. `fastBeforeSlowFinished=TIMEOUT`: client nhanh đã kết nối/gửi request và gọi đọc phản hồi, nhưng server còn đang chờ newline của client chậm. Timeout ở đây là **timeout đọc của fast**, không phải bằng chứng server hay TCP fast đã đóng.
2. `slowReply=ACK:SLOW`: khi main gửi newline còn thiếu cho slow, server hoàn tất `readLine()`, phản hồi và đóng socket slow.
3. `fastReply=ACK:FAST`: sau khi xử lý slow, server gọi `accept()` lần hai, đọc FAST và gửi phản hồi; chính kết nối của fast từ trước vẫn dùng được.
4. `serverOrder=[SLOW, FAST]`: thứ tự xử lý thực tế của server là tuần tự, dù FAST đã sẵn sàng trước khi SLOW kết thúc.

Trong ví dụ, `Executors.newSingleThreadExecutor()` chỉ cung cấp **một luồng để chạy vòng server** đồng thời với luồng main mô phỏng hai client. Nó không biến việc xử lý hai socket thành song song. `CountDownLatch` loại bỏ việc dựa hoàn toàn vào `Thread.sleep()` để quyết định client nào được nhận trước. Cổng `0` để hệ điều hành cấp một cổng tự do trên loopback. Các timeout 5 giây giới hạn thời gian kẹt trong môi trường thử; trên máy quá tải hoặc bị chặn mở socket, chương trình có thể ném exception thay vì in đúng ví dụ.

**Lưu ý về `readLine()`:** phương thức nhận dòng khi gặp LF, CR, CRLF hoặc EOF; nếu peer đóng output mà không gửi newline, `readLine()` có thể trả về phần ký tự còn lại. Trong demo, slow cố ý **giữ output mở** đến khi gửi newline, để tạo trạng thái chờ rõ ràng. Không được nhầm “không có newline” với “chắc chắn chờ vô hạn kể cả khi đã EOF”.

## 6. Các timeout giúp gì và còn thiếu gì?

Một biện pháp đầu tiên là cấu hình timeout để một client không thể giữ luồng **vô thời hạn trong một lần gọi blocking**:

~~~java
// Fragment minh họa trong handleClient(Socket client).
client.setSoTimeout(2_000); // 2 giây cho mỗi lần blocking read.
BufferedReader reader = new BufferedReader(
        new InputStreamReader(client.getInputStream(),
                StandardCharsets.UTF_8));
try {
    String line = reader.readLine();
    if (line == null) {
        // Peer đóng chiều gửi trước khi có request.
        return;
    }
    // Xử lý một dòng hợp lệ (cần kiểm tra độ dài/framing).
} catch (SocketTimeoutException timeout) {
    // Chủ động kết thúc phiên theo chính sách server.
    // try-with-resources ở caller sẽ đóng socket.
}
~~~

Đây là **fragment** nằm trong phương thức có quyền `return` và được gọi với socket đã kết nối; nó không phải chương trình Java hoàn chỉnh riêng. Một `SocketTimeoutException` cho biết thao tác đọc không nhận đủ dữ liệu trong khoảng chờ, **không tự động chứng minh peer đã mất kết nối**. Nếu quyết định đóng socket khi timeout, đó là chính sách của server.

Phải phân biệt ba loại thời hạn:

- **Read idle timeout:** `Socket.setSoTimeout` giới hạn thời gian đợi trong các lần blocking read ở tầng socket. Khi một client thỉnh thoảng gửi thêm dữ liệu, lời gọi `readLine` có thể tiếp tục nhận byte và chờ kết thúc dòng. Một idle timeout riêng lẻ không đảm bảo tổng thời gian phiên luôn nhỏ hơn một ngưỡng.
- **Overall request deadline:** đặt thời điểm muộn nhất để nhận đủ và xử lý request. Ví dụ, một request phải hoàn chỉnh trong 5 giây kể từ khi bắt đầu được phục vụ, bất kể có nhỏ giọt từng byte hay không. Cần đo thời gian đã qua và hủy/đóng khi quá hạn.
- **Processing / response deadline:** giới hạn công việc CPU, DB/API và giai đoạn trả dữ liệu. `setSoTimeout` **không** áp cho `OutputStream.write` hay mọi thao tác của server. Có thể cần deadline cấp ứng dụng hoặc I/O không chặn.

**Bắt buộc đặt giới hạn độ dài request:** một client gửi dòng dài vô hạn không có newline có thể làm `BufferedReader.readLine()` tích lũy dữ liệu vào bộ nhớ. Khi dùng giao thức theo dòng, phải kiểm tra tối đa số ký tự/byte, chấp nhận hoặc từ chối newline đúng quy tắc, và đặt deadline tổng. Nếu dùng frame có header độ dài, phải xác thực độ dài trước khi phân bổ bộ nhớ và kiểm tra phần body có đủ byte.

Các deadline chỉ **giới hạn tác hại mỗi client**, nhưng một server tuần tự vẫn phục vụ mỗi client một lần; khi có nhiều client chậm, thời gian chờ cộng dồn vẫn lớn.

## 7. Bản chất của head-of-line blocking và phạm vi ảnh hưởng

Không nên trộn ba hiện tượng:

| Hiện tượng | Ở lớp nào? | Ví dụ |
| --- | --- | --- |
| Head-of-line do **server tuần tự** | Luồng xử lý ứng dụng | Server đang `readLine(A)` nên không thể xử lý B |
| Head-of-line do **một TCP byte stream** | Thứ tự byte tin cậy trong cùng kết nối | Mất segment đầu có thể làm ứng dụng chờ byte trước dù dữ liệu sau đã tới |
| Hàng đợi backlog / scheduling | Kernel, scheduler, pool | TCP connection chờ ứng dụng accept hoặc chờ worker rảnh |

Bài này nhấn mạnh **loại thứ nhất**. Việc bổ sung thêm kết nối TCP chưa khắc phục được một luồng Java chỉ xử lý một kết nối tại một thời điểm. Ngược lại, tăng số worker cũng không làm thay đổi bản chất thứ tự byte của một TCP stream đơn lẻ.

Bên cạnh khả năng phục vụ, còn hai hệ quả:

- **Công bằng và độ trễ đuôi:** request nhanh đứng sau request chậm có thể nhận độ trễ không tương xứng với thời gian xử lý riêng của nó. Trung bình một client nhanh không giúp gì nếu nó thường phải xếp sau các client quá lâu.
- **Cạn hàng đợi/tài nguyên:** kết nối chờ sử dụng socket, file descriptor và bộ nhớ kernel; khi hàng đợi/pool đầy, hệ thống có thể từ chối hoặc trễ kết nối mới. Không dùng “tăng backlog” làm giải pháp duy nhất cho một endpoint bị giữ.

## 8. Những cách tổ chức server để giảm ảnh hưởng

### 8.1. Một worker riêng cho mỗi client

Một mẫu trực quan là luồng accept nhanh chóng giao socket cho worker:

~~~java
// Fragment minh họa nằm trong một method có ServerSocket server.
// handleClient(client) phải tự giới hạn thời gian, kích thước request.
while (running) {
    Socket client = server.accept();
    Thread worker = new Thread(() -> {
        try (client) {
            handleClient(client);
        } catch (IOException ex) {
            logClientFailure(ex);
        }
    });
    worker.start();
}
~~~

Khi A chậm, worker của A bị giữ, nhưng worker của B vẫn có cơ hội xử lý. Tuy nhiên, tạo một platform thread cho **mỗi** connection không giới hạn có thể cạn bộ nhớ, lịch CPU và file descriptor khi hàng nghìn client cùng chờ. Đoạn trên là minh họa chiến lược, **không phải thiết kế an toàn hoàn chỉnh**.

### 8.2. Pool worker có giới hạn và hàng đợi có giới hạn

Với Java 17, có thể tách luồng accept khỏi luồng xử lý bằng `ThreadPoolExecutor`:

~~~java
// Fragment bên trong method có ServerSocket server.
// imports: java.net.Socket, java.util.concurrent.*
// handleClient(Socket) phải do ứng dụng cung cấp.
ThreadPoolExecutor workers = new ThreadPoolExecutor(
        4, 4,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(16),
        new ThreadPoolExecutor.AbortPolicy());

try {
    while (!Thread.currentThread().isInterrupted()) {
        Socket client = server.accept();
        try {
            workers.execute(() -> {
                try (client) {
                    client.setSoTimeout(2_000);
                    handleClient(client);
                } catch (Exception ex) {
                    // Log lỗi và áp dụng chính sách kết thúc client.
                    recordFailure(ex);
                }
            });
        } catch (RejectedExecutionException overloaded) {
            // Pool và queue đã đầy: không giữ client vô hạn.
            client.close();
        }
    }
} finally {
    workers.shutdown();
}
~~~

Đây là **fragment triển khai mẫu**, cần đặt vào class, cung cấp `handleClient` và `recordFailure`, bổ sung xử lý lỗi listener, ngắt vòng lặp và shutdown hoàn chỉnh trước khi dùng thật.

Trong thiết kế này:

1. Luồng `accept()` giao client cho pool và có thể nhận connection tiếp theo sớm hơn.
2. Tối đa bốn worker xử lý cùng lúc; 16 tác vụ chờ trong queue **không được xử lý ngay**.
3. Nếu đã đủ bốn worker và queue đầy, `execute()` ném `RejectedExecutionException` theo `AbortPolicy`; ứng dụng đóng socket vừa nhận để không bỏ rơi tài nguyên.
4. Nếu client chậm giữ cả bốn worker, client khác vẫn có thể chờ rất lâu hoặc bị từ chối. Pool **giảm mức độ chặn toàn hệ thống**, không loại bỏ nhu cầu timeouts, admission control và giới hạn tài nguyên.
5. Hàng đợi chứa socket đang mở: cần xem xét timeout từ lúc kết nối, giới hạn thời gian chờ trước xử lý, và dọn socket còn tồn trong hàng đợi khi shutdown. Một lệnh `workers.shutdown()` tự nó không xử lý hết mọi kịch bản đóng socket hoặc yêu cầu đang chờ.

Tránh dùng `CallerRunsPolicy` một cách vô thức trong luồng `accept()`: khi pool đầy, chính luồng accept sẽ chạy `handleClient`, vô tình đưa blocking trở lại vòng chấp nhận kết nối.

### 8.3. I/O không chặn với `Selector`

Java NIO có `ServerSocketChannel`, `SocketChannel` và `Selector` để một hoặc một nhóm event loop theo dõi nhiều kết nối sẵn sàng đọc/ghi. Khi client A không có dữ liệu, event loop có thể xử lý client B thay vì đứng chờ blocking read của A.

Cách này đòi hỏi state machine, buffer riêng từng client, xử lý partial read/write, framing, sự kiện `OP_READ`/`OP_WRITE` và backpressure. Nếu callback trong event loop xử lý CPU/DB lâu, nó **vẫn có thể chặn** các connection khác; công việc blocking nên đưa ra worker thích hợp.

### 8.4. Virtual threads trên Java 21+

Với Java 21+, virtual thread cho phép giữ cách lập trình blocking dễ đọc mà có thể phục vụ nhiều phiên đồng thời hơn:

~~~java
// Fragment Java 21+; không biên dịch trên Java 17.
// ServerSocket server và handleClient(Socket) đã được cung cấp.
while (running) {
    Socket client = server.accept();
    Thread.startVirtualThread(() -> {
        try (client) {
            handleClient(client);
        } catch (IOException ex) {
            recordFailure(ex);
        }
    });
}
~~~

Virtual thread giảm chi phí thread của nhiều tác vụ đợi I/O, **không** khiến socket/heap, connection DB, CPU hay dịch vụ phía sau trở nên vô hạn. Cần giới hạn số connection/request, thời gian sống, kích thước input và tài nguyên; tránh giữ monitor trong đoạn blocking lâu ở các trường hợp có thể gây pinning và kiểm tra hành vi trên phiên bản JDK thực tế.

**Ranh giới phiên bản:** ví dụ `SequentialProof.java` và pool giới hạn áp dụng Java 17+; `Thread.startVirtualThread` là API Java 21+, không được dùng khi yêu cầu chạy trên Java 17.

## 9. Chọn mô hình phù hợp với bài toán

| Mô hình | Ưu điểm | Rủi ro / chi phí | Khi phù hợp |
| --- | --- | --- | --- |
| Tuần tự, một luồng | Dễ học, ít trạng thái dùng chung | Một client chậm giữ mọi client đứng sau; thông lượng thấp khi I/O blocking | Demo, công cụ nội bộ rất ít client, giao thức kiểm soát chặt |
| Platform thread per client | Cô lập chờ I/O giữa client | Rất nhiều thread gây chi phí bộ nhớ/scheduler | Client ít hoặc giới hạn rõ số phiên |
| Fixed/limited worker pool | Kiểm soát số luồng/tác vụ và có chính sách overload | Queue wait, từ chối tải, nguy cơ nghẽn toàn pool | TCP server Java 17+ cần phục vụ đồng thời với giới hạn |
| NIO selector/event loop | Quản lý nhiều kết nối chờ I/O | Trạng thái/framing/backpressure phức tạp; callback blocking gây nghẽn | Số lượng kết nối lớn, lưu lượng I/O phù hợp |
| Virtual thread per connection | Giữ code blocking dễ hiểu, nhẹ hơn platform thread trong nhiều I/O wait | Vẫn cần hạn chế socket/bộ nhớ/CPU/tài nguyên đích | Java 21+ với nhiều client chờ I/O |

Không có mô hình nào loại bỏ hoàn toàn request chậm. Cần **giới hạn tác hại của client riêng lẻ và bảo vệ nguồn lực chung**. Nếu pool chỉ có bốn worker và cả bốn bị giữ bởi bốn request “nhỏ giọt”, hành vi nghẽn vẫn tồn tại dù không còn một luồng duy nhất.

## 10. Checklist quan sát và chẩn đoán khi server bị nghẽn

Khi client B báo “connect được nhưng không có phản hồi”, kiểm tra theo thứ tự:

1. **Thời điểm:** ghi timestamp connection được kernel accept, Java `accept()` trả về, bắt đầu xử lý, nhận đủ request, hoàn thành response. Tách thời gian chờ trước xử lý khỏi thời gian xử lý.
2. **Thread dump:** xem luồng phục vụ có đứng tại `SocketInputStream.read`, `BufferedReader.readLine`, `SocketOutputStream.write`, truy vấn DB hay mã CPU. Không vội kết luận do mạng nếu thực tế nghẽn DB.
3. **Framing:** client đã gửi newline, độ dài đã khai báo, EOF hoặc marker kết thúc chưa? Giao thức có đợi một bên đóng output trước khi trả lời, trong khi bên kia cũng đang đợi response không?
4. **Timeout và deadline:** `setSoTimeout` có cấu hình không, có tổng deadline và max request size không, có client gửi từng byte để vượt idle timeout không?
5. **Hàng đợi và độ quá tải:** số socket đang xử lý, kết nối chờ accept, độ sâu queue worker, số task active, thời gian queue, tỉ lệ reject, số file descriptor và bộ nhớ.
6. **Đóng tài nguyên:** mọi socket accepted được đóng trong `try-with-resources` hoặc `finally` chưa? Khi timeout, client ngắt bất thường hoặc từ chối task, connection có bị giữ lại không?
7. **Biện pháp:** thử một client slow có kiểm soát trên loopback/staging và quan sát thời gian phản hồi của một client nhanh đến sau. So sánh khi dùng pool giới hạn với cấu hình deadline/framing tương đương.

Những chỉ số hữu ích là **thời gian chờ đến khi được phục vụ**, thời gian đọc request, thời gian xử lý, thời gian ghi response, số connection đang hoạt động, tỉ lệ timeout và tỉ lệ overload. Chỉ đo tổng latency sẽ khó xác định nghẽn do thứ tự tuần tự hay do xử lý mỗi request.

## 11. Những hiểu nhầm thường gặp

1. **“Client đã kết nối TCP thành công thì server Java đang xử lý nó.”** Sai: kết nối có thể nằm trong hàng đợi chờ `accept()`, hoặc đã accept nhưng vẫn chờ worker.
2. **“Tăng backlog là giải quyết được client chậm.”** Sai: backlog giúp quản lý hàng đợi ở kernel, không tạo thêm luồng xử lý ứng dụng.
3. **“Chỉ `readLine()` mới gây blocking.”** Sai: `read()`, `readNBytes()`, `write()` và công việc DB/CPU đều có thể kéo dài phiên.
4. **“Đặt `Socket.setSoTimeout(2000)` giới hạn toàn bộ request hai giây.”** Sai: nó giới hạn việc chờ ở blocking read; byte nhỏ giọt và xử lý sau đọc vẫn có thể kéo dài tổng thời gian.
5. **“`ServerSocket.setSoTimeout` xử lý client chậm.”** Sai: nó chỉ giới hạn việc chờ **kết nối mới** ở `accept()`, không giới hạn socket đã nhận.
6. **“Việc `write()` thành công chứng minh client đã xử lý response.”** Sai: dữ liệu có thể mới đi vào buffer cục bộ; cần bằng chứng ở cấp giao thức nếu nghiệp vụ đòi hỏi.
7. **“Thread per client có thể tăng vô hạn.”** Sai: thread, socket, CPU, memory, DB connection và scheduler đều hữu hạn.
8. **“NIO luôn nhanh hơn với mọi ứng dụng.”** Không có kết luận đó: event loop phù hợp với tải nhất định nhưng cần thiết kế không blocking và quản lý buffer/backpressure cẩn thận.
9. **“Có virtual threads thì không cần giới hạn request.”** Sai: virtual thread không giới hạn số connection/socket và tải hệ thống phía sau.
10. **“Một client chậm làm tất cả client rớt kết nối ngay.”** Không nhất thiết: nhiều client vẫn có thể giữ TCP connection nhưng phải chờ xử lý ứng dụng; khi quá tải lâu hoặc hàng đợi đầy, một số kết nối mới có thể trễ, timeout hoặc bị từ chối tùy môi trường.

## 12. Tự kiểm tra

**Câu 1.** Server gọi `accept(A)`, rồi `readLine(A)`. A gửi `hello` nhưng không gửi newline hay FIN. B đã `connect()` thành công và gửi `PING\\n`. Vì sao B chưa có phản hồi?  
**Đáp án:** Server đang xử lý tuần tự và bị giữ trong `readLine(A)`; nó chưa gọi `accept(B)` và chưa đọc request của B, dù TCP B có thể đã thiết lập và đệm dữ liệu.

**Câu 2.** Nếu tăng backlog từ 50 lên 500, số request server có thể xử lý đồng thời thành 500 không?  
**Đáp án:** Không. Backlog liên quan hàng đợi kết nối của kernel; server tuần tự vẫn chỉ có một luồng xử lý yêu cầu tại một thời điểm.

**Câu 3.** `setSoTimeout(1000)` có chống được client gửi mỗi 900 ms một byte trong khi request dài không giới hạn không?  
**Đáp án:** Không bảo đảm. Đây là read inactivity timeout; cần thêm tổng deadline và giới hạn kích thước/frame.

**Câu 4.** Trong demo, `fastBeforeSlowFinished=TIMEOUT` có nghĩa TCP fast đã chết không?  
**Đáp án:** Không. Chính socket fast vẫn có thể nhận `ACK:FAST` sau khi server xử lý xong slow; timeout là thời gian chờ đọc của client fast.

**Câu 5.** Khi chuyển sang pool bốn worker, một client chậm có còn ảnh hưởng người khác không?  
**Đáp án:** Có thể, nhưng nó thường chỉ chiếm một worker. Nếu bốn worker đều bị giữ hoặc queue đầy, những client khác vẫn chờ hoặc bị từ chối theo chính sách overload.

**Câu 6.** Khi nào dùng NIO selector hoặc virtual threads?  
**Đáp án:** Khi cần quản lý nhiều kết nối chờ I/O đồng thời. NIO đòi hỏi state machine và event loop không blocking; virtual threads yêu cầu Java 21+ và vẫn cần giới hạn tài nguyên.

## Tài liệu đối chiếu

- Java SE 17 — `ServerSocket`, `accept()`, `setSoTimeout()`, backlog: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- Java SE 17 — `Socket`, `connect()`, `setSoTimeout()` và stream I/O: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html
- Java SE 17 — `BufferedReader.readLine()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html
- Java SE 17 — `ThreadPoolExecutor` và chính sách từ chối: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Java SE 17 — `Selector` và NIO: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html
- Java SE 21 — `Thread.startVirtualThread()`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html
