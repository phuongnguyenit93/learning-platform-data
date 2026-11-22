# Tạo máy khách gửi chậm để kiểm chứng timeout và giới hạn tài nguyên (Java 17+)

## 1. Một request gửi chậm có thể gây ra điều gì?

Một HTTP server không chỉ tiêu tốn CPU khi thực thi nghiệp vụ. Ngay từ lúc chấp nhận kết nối, nó có thể phải giữ **TCP socket, bộ đệm, trạng thái parser, thread hoặc event-loop slot** trong khi chờ client gửi request line, headers và request body. Nếu client gửi rất chậm — hoặc chỉ gửi vài byte rồi im lặng — một kết nối có thể giữ tài nguyên lâu hơn dự tính.

Tình huống thực tế gồm: thiết bị di động mạng yếu, client upload qua mạng không ổn định, client ngừng giữa request vì ứng dụng bị treo, reverse proxy/người dùng hủy upload, hoặc request headers đi qua kết nối gần như không có tốc độ. Server cần vừa chấp nhận client chậm hợp lệ vừa có **deadline, giới hạn bytes và giới hạn concurrency** để không bị chiếm dụng vô hạn.

Bài này thuộc **Java Advance - networking → Thực nghiệm mạng** và giải đúng đề bài **“Tạo máy khách gửi chậm để kiểm chứng timeout và giới hạn tài nguyên”**. Chúng ta viết **máy khách gửi chậm có kiểm soát trên loopback**, **server thử nghiệm nhỏ** và **bộ kiểm thử có thể biên dịch/chạy bằng Java 17**. Mục tiêu là kiểm chứng cơ chế phòng vệ, không tạo traffic ồ ạt hoặc gây gián đoạn dịch vụ bên ngoài.

### 1.1. Mô hình một kết nối bị gửi chậm

~~~text
    SLOW CLIENT                                 TCP SERVER
        |                                            |
        |--- TCP connect --------------------------->|  accept
        |                                            |  giữ socket
        |--- "G" ----------------------------------->|  read 1 byte
        |      ... nghỉ 90 ms                        |  chờ tiếp
        |--- "E" ----------------------------------->|  read 1 byte
        |      ... nghỉ 90 ms                        |  chờ tiếp
        |--- "T" ----------------------------------->|  read 1 byte
        |                                            |
        |   mỗi lần chờ < idle read timeout          |
        |   nhưng tổng thời gian có thể rất dài      |
        |                                            |
        |<--- timeout / close -----------------------|  total deadline
        |                                            |  release slot
~~~

**Điểm quan trọng:** một **idle timeout** tính lại cho mỗi lần đọc có thể không phát hiện một client cứ gửi 1 byte trước khi timeout hết hạn. Muốn bảo vệ tổng thời gian nhận request, cần **absolute request deadline** tính từ một mốc xác định, bên cạnh **idle-gap timeout**.

### 1.2. Slow sender không giống slow receiver

| Tình huống | Client làm gì? | Server dễ bị giữ tài nguyên ở đâu? |
| --- | --- | --- |
| **Slow sender / slow reader input** | Gửi request line/headers/body rất chậm | Server đang chờ **đọc request bytes** |
| **Slow receiver** | Server gửi response nhưng client đọc rất chậm | Server đang **ghi response**, send buffer đầy |
| **Request rất lớn** | Client gửi nhiều bytes, có thể vẫn nhanh | Heap, parser, disk, quota, CPU |
| **Nhiều kết nối đồng thời** | Client mở nhiều sockets | File descriptors, active handlers, thread/executor queue |
| **Ứng dụng server xử lý lâu** | Request có thể đã gửi đầy đủ | Backend DB/service, CPU, locks |

Bài này tập trung vào **slow sender** và cách đo **read timeout / total deadline / request-size / active connection budget**. Timeout của response write là một vấn đề khác; đừng dùng quan sát của bài này để kết luận toàn bộ network stack đã được bảo vệ.

## 2. Mục tiêu học tập

Sau khi hoàn tất bài, bạn sẽ:

1. Tạo được client Java gửi **request-line hoặc header theo từng byte có khoảng nghỉ** qua `Socket`, không cần server bên ngoài.
2. Tạo được client **gửi vài bytes rồi ngừng** để kiểm tra server read idle timeout.
3. Phân biệt `ServerSocket.setSoTimeout(...)` đối với `accept()` và `Socket.setSoTimeout(...)` đối với **blocking `InputStream.read()`**.
4. Thấy bằng thử nghiệm một byte trickle có thể vượt qua idle-gap timeout nhưng bị **total request deadline**.
5. Thiết lập **max request header bytes**, **max body/frame size**, và kiểm tra limit **trước khi allocate**.
6. Kiểm thử một **Semaphore** giới hạn active handlers và quan sát request thứ hai bị từ chối khi slot đã bị chiếm.
7. Xác minh slot, executor và sockets **được giải phóng** khi timeout, reject hoặc client hoàn tất request.
8. Giải thích tại sao **TCP connect thành công** không bảo đảm HTTP request hoàn chỉnh.
9. Biết khi nào server chọn HTTP 408/431/413, khi nào đóng kết nối mà **không có response hợp lệ**.
10. Biết cách chọn idle timeout, total timeout, min data rate, quota và overload policy theo workload, tránh loại oan người dùng mạng chậm.
11. Thiết kế fault-injection tests có đồng bộ `CountDownLatch`/`Future`, không phụ thuộc ngẫu nhiên vào tốc độ hệ điều hành.
12. Quan sát metrics: active connections, wait time, bytes received, idle/total expiration, size rejects và cleanup.
13. Hiểu những giới hạn của các ví dụ raw TCP/HTTP tối giản so với `com.sun.net.httpserver.HttpServer` hoặc production gateway.

## 3. Các giới hạn cần đo riêng

### 3.1. So sánh deadline và capacity

| Giới hạn | Tính từ mốc nào? | Chặn nguy cơ gì? |
| --- | --- | --- |
| **Accept wait timeout** | Mỗi lần `ServerSocket.accept()` chờ connection mới | Server test không treo khi không có client |
| **Idle read timeout** | Một lời gọi blocking `InputStream.read()` chờ byte tiếp theo | Client ngừng gửi trong một khoảng |
| **Total header deadline** | Từ lúc bắt đầu nhận headers tới kết thúc CRLFCRLF | Client gửi đều đặn nhưng **quá chậm tổng thể** |
| **Total request/body deadline** | Từ mốc request/body nhận được xác định | Upload kéo dài vô hạn qua tiny chunks |
| **Max header bytes/count** | Tổng bytes/fields đã parse | Header rất lớn, parser/memory exhaustion |
| **Max body bytes** | Số bytes thực nhận hoặc khai báo được xác minh | Allocate/stream tới disk không hạn mức |
| **Min upload rate** | Một cửa sổ đo dài hơn jitter và TLS pauses | Slow trickle duy trì dài hạn |
| **Max active connections/handlers** | Slots đang dùng | Nhiều slow clients giữ threads/file descriptors |
| **Bounded work queue** | Số tasks chờ handler | Executor tạo backlog vô hạn |
| **Idle keep-alive timeout** | Kết nối đã xử lý xong một request chờ request tiếp | Tốn sockets khi connection không hoạt động |
| **Max response write time** | Gửi response tới client chậm nhận | OutputStream bị chặn / outbound buffers |
| **Max lifetime / global budget** | Tuổi connection hoặc tổng tài nguyên đang giữ | Tài nguyên bị giữ mãi qua nhiều exchanges |

**Không dùng một timeout duy nhất cho mọi phase.** Ví dụ `Socket.setSoTimeout(250)` không tự đặt total HTTP request timeout 250 ms; mỗi successful read có thể làm client được chờ thêm. Tương tự `ServerSocket.setSoTimeout(5000)` không hề có nghĩa accepted socket chỉ được sống 5 giây.

### 3.2. Idle-gap timeout khác total deadline

Giả sử idle timeout 250 ms, absolute deadline 650 ms:

~~~text
Time (ms):    0      90      180     270     360     450    540     650
Client:       G ---- E ----- T ----- ' ' ---- / ---- ' ' --- H ----- (dừng)
Idle gap:     90     90      90      90      90      90       <250
Total age:    ------------------------------------------------->650

Idle timeout đơn lẻ: chưa hết hạn trong suốt giai đoạn mỗi byte đến.
Total deadline: request chưa đủ CRLFCRLF tại 650 ms -> reject.
~~~

Một client gửi đều một byte mỗi 100 ms có thể ở trạng thái “vừa mới gửi byte” suốt hàng phút. Phòng vệ dựa vào **deadline từ lúc bắt đầu request** để tránh sự kéo dài vô hạn. Trong bài lab, chúng ta dùng `System.nanoTime()` cho elapsed-time; production không nên dùng `System.currentTimeMillis()` làm đồng hồ đơn điệu vì NTP/clock corrections.

### 3.3. Header byte cap khác body byte cap

- Header request line và header fields bị giới hạn trước khi server chuyển sang đọc body.
- Với HTTP/1.1, **CRLFCRLF** kết thúc header section; nếu có `Content-Length`/chunked request, body nằm sau đó.
- Body size phải được kiểm tra theo **bytes thực nhận**, không chỉ tin `Content-Length` do client gửi.
- Nếu body dùng compression, có thể cần giới hạn cả **encoded bytes** lẫn **decompressed bytes**.
- Server không được cấp phát `new byte[declaredContentLength]` trước khi xác minh length hợp lệ và nằm trong quota.
- Đóng connection sớm có thể ngăn client hoàn tất upload, nhưng lỗi sau response/close cần được quản lý để không giữ sockets/thrashing.

## 4. Chuẩn bị thí nghiệm an toàn

Thí nghiệm chỉ chạy trên máy của bạn:

- Máy chủ test bind **`127.0.0.1`** (loopback), cổng `0` để hệ điều hành tự chọn một cổng trống.
- Mỗi case dùng tối đa một hoặc vài kết nối; **không** quét host, không mở hàng nghìn sockets.
- Timeout của test ngắn tính bằng mili-giây để kết thúc có kiểm soát; **không dùng các giá trị này làm mặc định production**.
- Sử dụng `Future.get(timeout)` và `CountDownLatch.await(timeout)` để test không treo vô hạn.
- Tự đóng `Socket`, `ServerSocket`, dừng `ExecutorService` trong `finally`.
- Không gửi request giả lập chậm tới API công cộng hay hệ thống không được phép. Đặc biệt, stress/probing hàng loạt tới dịch vụ bên ngoài có thể làm ảnh hưởng người dùng thật.
- Ghi rõ từng kết quả thành công là bằng chứng **cho server thử nghiệm cụ thể**; implementation khác có thể trả status khác hoặc đóng TCP không gửi HTTP response.

Yêu cầu môi trường:

~~~bash
java -version
javac -version
~~~

Dùng **JDK 17 trở lên**. Các chương trình dưới đây dùng `switch` expression và Java records, biên dịch bằng `javac --release 17`; không cần thư viện Maven/Gradle, Docker, TLS certificate hay Internet.

## 5. Điều khiển tốc độ gửi bằng Socket

### 5.1. Gửi request theo byte

Một `HttpClient` cấp cao tự quản lý nhiều chi tiết framing/headers, rất phù hợp ứng dụng HTTP bình thường nhưng **không tiện để kiểm soát từng byte của request-line và thời điểm xuống dòng**. Để thử tình huống client gửi chậm ở mức wire, dùng `Socket.getOutputStream()`:

~~~java
try (Socket client = new Socket("127.0.0.1", port)) {
    OutputStream out = client.getOutputStream();
    byte[] request = "GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"
            .getBytes(StandardCharsets.US_ASCII);

    for (byte b : request) {
        out.write(b);
        out.flush();
        Thread.sleep(90);  // Lab only: kiểm soát tốc độ gửi.
    }
}
~~~

Đây là **mảnh code minh họa**, chưa có `port`, imports hoặc server, không phải chương trình độc lập. Nó nhấn mạnh khả năng **flush và chèn khoảng nghỉ** theo ý test.

**Cẩn trọng với thí nghiệm thật:** TCP có thể gộp hoặc chia gói; `write(1 byte)` không đảm bảo một TCP segment một byte trên wire. `TCP_NODELAY` có thể thay hành vi Nagle, nhưng bản chất thử nghiệm là **server quan sát được các byte đến chậm**, không cần khẳng định mỗi write tạo một packet.

### 5.2. Gửi một ít rồi không gửi tiếp

~~~java
out.write("GET /".getBytes(StandardCharsets.US_ASCII));
out.flush();
Thread.sleep(500); // Dừng gửi trước khi headers đầy đủ.
~~~

Nếu server chờ đọc byte kế và đặt idle read timeout 250 ms, nó có thể timeout trước khi client bắt đầu gửi tiếp. **Không cần đóng socket ngay** để thử kiểu này; đóng socket sẽ tạo EOF thay vì chứng minh timeout do peer vẫn kết nối nhưng im lặng.

### 5.3. Gửi đúng protocol không nằm trong scope parser demo

Một raw HTTP request hoàn chỉnh cần request line, headers và dòng trống CRLFCRLF; nếu có body cần framing hợp lệ theo HTTP. Các ví dụ dưới đây **chủ ý chỉ kiểm tra boundary header** hoặc **dùng protocol length-prefixed riêng**. Không xem parser vài chục dòng như một HTTP server hoàn chỉnh.

## 6. Demo #1 — gửi HTTP headers nhanh, im lặng, nhỏ giọt và quá cỡ

### 6.1. Các case trong chương trình

Demo dựng bốn test độc lập, mỗi test có một `ServerSocket` loopback port tạm và **một client**:

| Case | Hành vi client | Cơ chế server kiểm thử | Kết quả dự kiến |
| --- | --- | --- | --- |
| `FAST` | Gửi nguyên HTTP headers ngay | Có đủ CRLFCRLF dưới giới hạn | `200 COMPLETE` |
| `IDLE` | Gửi `GET /` rồi dừng 350 ms | Idle limit 250 ms | `408 IDLE_TIMEOUT` |
| `TRICKLE` | Gửi từng byte cách 90 ms, không kết thúc headers | Idle gap <250 ms nhưng tổng vượt 650 ms | `408 TOTAL_TIMEOUT` |
| `OVERSIZE` | Gửi đủ 64 bytes header không có CRLFCRLF | Header limit 64 bytes | `431 HEADER_LIMIT` |

Bộ server thử nghiệm chỉ đọc byte đến marker CRLFCRLF, **không parser method, Host, Content-Length, chunked body hay multiple requests**. Nó tự trả response HTTP/1.1 nhỏ với `Connection: close` và `Content-Length: 0` để client lấy status. Mã 408 và 431 minh họa một **policy test**; server production có thể chọn đóng connection khi input thiếu, thậm chí không phát ra response nếu socket đã hỏng.

### 6.2. Tệp đầy đủ `SlowHeaderClientLab.java`

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public class SlowHeaderClientLab {
    static final int IDLE_MS = 250;
    static final int TOTAL_MS = 650;
    static final int MAX_HEADER_BYTES = 64;
    enum Trial { FAST, IDLE, TRICKLE, OVERSIZE }

    static String respond(Socket peer, int status, String label) throws IOException {
        OutputStream out = peer.getOutputStream();
        String response = "HTTP/1.1 " + status + " " +
                (status == 200 ? "OK" : status == 408 ? "Request Timeout" :
                 status == 431 ? "Request Header Fields Too Large" : "Bad Request") +
                "\r\nConnection: close\r\nContent-Length: 0\r\n\r\n";
        out.write(response.getBytes(StandardCharsets.US_ASCII));
        out.flush();
        return label;
    }

    static String serveOne(ServerSocket server) throws IOException {
        try (Socket peer = server.accept()) {
            InputStream in = peer.getInputStream();
            long deadline = System.nanoTime() +
                    TimeUnit.MILLISECONDS.toNanos(TOTAL_MS);
            int state = 0, count = 0;
            while (true) {
                long remainingNs = deadline - System.nanoTime();
                if (remainingNs <= 0) return respond(peer, 408, "TOTAL_TIMEOUT");
                int untilTotalMs = (int)Math.max(1,
                        TimeUnit.NANOSECONDS.toMillis(remainingNs));
                peer.setSoTimeout(Math.min(IDLE_MS, untilTotalMs));
                int b;
                try {
                    b = in.read();
                } catch (SocketTimeoutException timeout) {
                    return respond(peer, 408,
                            System.nanoTime() >= deadline ?
                            "TOTAL_TIMEOUT" : "IDLE_TIMEOUT");
                }
                if (b == -1) return respond(peer, 400, "INCOMPLETE");
                count++;
                state = switch (state) {
                    case 0 -> b == '\r' ? 1 : 0;
                    case 1 -> b == '\n' ? 2 : b == '\r' ? 1 : 0;
                    case 2 -> b == '\r' ? 3 : 0;
                    default -> b == '\n' ? 4 : b == '\r' ? 1 : 0;
                };
                if (state == 4) return respond(peer, 200, "COMPLETE");
                if (count >= MAX_HEADER_BYTES) {
                    return respond(peer, 431, "HEADER_LIMIT");
                }
            }
        }
    }

    static void run(Trial trial, ExecutorService worker) throws Exception {
        try (ServerSocket server = new ServerSocket(0, 1,
                InetAddress.getByName("127.0.0.1"))) {
            server.setSoTimeout(5000);
            Future<String> outcome = worker.submit(() -> serveOne(server));
            try (Socket client = new Socket("127.0.0.1",
                    server.getLocalPort())) {
                client.setSoTimeout(3000);
                OutputStream out = client.getOutputStream();
                switch (trial) {
                    case FAST -> out.write(
                            "GET /ok HTTP/1.1\r\nHost: localhost\r\n\r\n"
                                    .getBytes(StandardCharsets.US_ASCII));
                    case IDLE -> {
                        out.write("GET /".getBytes(StandardCharsets.US_ASCII));
                        out.flush();
                        Thread.sleep(IDLE_MS + 100);
                    }
                    case TRICKLE -> {
                        byte[] prefix = "GET / H".getBytes(StandardCharsets.US_ASCII);
                        for (int i = 0; i < prefix.length; i++) {
                            out.write(prefix[i]);
                            out.flush();
                            if (i + 1 < prefix.length) Thread.sleep(90);
                        }
                    }
                    case OVERSIZE -> {
                        out.write("A".repeat(MAX_HEADER_BYTES)
                                .getBytes(StandardCharsets.US_ASCII));
                    }
                }
                out.flush();
                String status = new BufferedReader(
                        new InputStreamReader(client.getInputStream(),
                                StandardCharsets.US_ASCII)).readLine();
                System.out.println(trial + ": " + status + " | " +
                        outcome.get(3, TimeUnit.SECONDS));
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try {
            for (Trial trial : Trial.values()) run(trial, worker);
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 SlowHeaderClientLab.java
java SlowHeaderClientLab
~~~

**Stdout đã kiểm chứng khi chạy trên JDK 24 với `javac --release 17`:**

~~~text
FAST: HTTP/1.1 200 OK | COMPLETE
IDLE: HTTP/1.1 408 Request Timeout | IDLE_TIMEOUT
TRICKLE: HTTP/1.1 408 Request Timeout | TOTAL_TIMEOUT
OVERSIZE: HTTP/1.1 431 Request Header Fields Too Large | HEADER_LIMIT
~~~

Đây là kết quả chạy thực tế. Timer phụ thuộc hệ điều hành, scheduler, GC và tải máy; trong môi trường rất bận, **thời điểm từng byte đến có thể chênh**, nên các test timing ngắn có thể khác kết quả. Tăng margin khi viết CI test và ưu tiên clock giả lập cho state machine, không lấy các số 250/650 ms làm production defaults.

### 6.3. Phân tích dòng `FAST`

- Client gửi `GET /ok HTTP/1.1\r\nHost: localhost\r\n\r\n` đủ header terminator.
- Server đọc từng byte và cập nhật 4-state matcher cho `\r\n\r\n`.
- Nó trả `200 OK` và nhãn test `COMPLETE`.
- Không có handler cho `/ok` hay application logic: đây là **header-boundary test**, 200 chỉ là kết quả giả lập.

### 6.4. Phân tích dòng `IDLE`

- Client gửi một phần `GET /`, chưa đủ CRLFCRLF.
- Sau đó nó không gửi bytes mới trong hơn `IDLE_MS=250` ms nhưng **giữ TCP socket mở**.
- `InputStream.read()` trong server đã được đặt `Socket.setSoTimeout(250)` nên ném `SocketTimeoutException`.
- Server gửi 408 và nhãn `IDLE_TIMEOUT`, rồi try-with-resources đóng accepted socket.

Đây khác với client đóng ngay sau khi gửi vài bytes: khi client đóng đúng TCP, server thường thấy **EOF -1** hoặc error, không phải socket idle timeout.

### 6.5. Phân tích dòng `TRICKLE`

- Client gửi 7 bytes của `GET / H`, mỗi byte cách nhau 90 ms.
- Khoảng chờ giữa các bytes nhỏ hơn idle timeout 250 ms.
- Server vẫn theo dõi absolute deadline 650 ms kể từ lúc bắt đầu nhận headers.
- Sau khi byte cuối tới, server chờ byte kế nhưng remaining time cho total deadline ngắn hơn idle timeout. Khi hết tổng thời gian, server trả 408 và nhãn `TOTAL_TIMEOUT`.

**Nếu server chỉ có `setSoTimeout(250)` mà không có total deadline**, một client có thể gửi byte trước mỗi mốc 250 ms và giữ connection rất lâu. Đây là lý do test quan trọng.

### 6.6. Phân tích dòng `OVERSIZE`

- Client gửi đúng 64 ký tự `A` mà không có header terminator.
- Server tăng `count` cho mỗi byte và khi `count >= MAX_HEADER_BYTES` thì từ chối.
- Nó không đọc vô hạn, không xây `StringBuilder` khổng lồ và không đợi thêm byte vô thời hạn.
- Response thử nghiệm là 431 `Request Header Fields Too Large`.

Trong production, header budget thường gồm request line + header fields, số lượng fields, encoded byte count và parser semantics. Ví dụ không thực hiện full HTTP/1.1 validation — vì vậy việc đặt status 431 là **kết quả policy của lab**, không phải lời hứa mọi server JDK sẽ trả 431 theo cách y hệt.

### 6.7. Vai trò của hai loại timeout trong mã

~~~java
server.setSoTimeout(5000); // Chỉ ảnh hưởng ServerSocket.accept().

// Sau khi accept:
peer.setSoTimeout(250);    // Ảnh hưởng blocking reads trên Socket InputStream.
~~~

Hai dòng trên là **mảnh code**, không chạy độc lập. `ServerSocket` và `Socket` là hai objects khác nhau:

- `ServerSocket.setSoTimeout`: `accept()` chờ tối đa thời gian đặt; nếu không có kết nối mới, ném `SocketTimeoutException` nhưng listener vẫn còn hợp lệ.
- `Socket.setSoTimeout`: blocking `InputStream.read()` trên accepted socket chỉ chờ tối đa thời gian đặt; khi timeout, socket **không tự động đóng**.
- Cả hai **không tự đặt write timeout** cho `OutputStream.write(...)`.
- `setSoTimeout(0)` được hiểu là chờ vô thời hạn cho operation tương ứng; lab luôn chọn giá trị hữu hạn.
- Đừng hiểu timeout 250 ms của một `read()` là server đã có total request budget 250 ms.

## 7. Từ timeout tới giới hạn tài nguyên: mỗi accepted connection có giá

Ngay khi `ServerSocket.accept()` thành công, server có thể phải giữ:

- Một file descriptor/socket.
- Input/output buffers và transport state.
- Một task/thread/continuation xử lý request.
- Bộ nhớ để parse request header/body.
- Đối tượng request context, authentication state, timer và logs.
- Connection pool/quota entry cho user hoặc IP.
- Có thể cả TLS state và handshake buffers nếu dùng HTTPS.

Một client chậm có thể giữ resources **trước khi business handler được gọi**. Ví dụ HTTP parser thường phải nhận đủ request line và headers trước khi tạo request object; nếu chỉ giới hạn handler concurrency, các incomplete requests có thể vẫn giữ connection state ở tầng listener/parser.

**Do đó phải có cả lớp pre-handler protection** (connection cap, header deadline, header count/bytes, TLS handshake deadline, idle keepalive) và lớp handler protection (body size/time, executor bounded queue, app concurrency cap, downstream deadlines).

### 7.1. Sơ đồ admission control

~~~text
TCP accept
    |
    v
connection admission: global/per-client cap
    |
    +----> full? reject/close sớm
    |
    v
TLS/HTTP header parsing with own deadlines and byte caps
    |
    v
handler/work queue admission
    |
    +----> full? 429/503/close theo contract
    |
    v
body streaming with deadline + size cap
    |
    v
business processing with timeout/quotas
    |
    v
response write / cleanup
~~~

Giới hạn **server backlog** không phải là giới hạn active handlers. Tham số backlog của `ServerSocket` là gợi ý cho hàng đợi chờ accept ở transport/OS, không dùng thay `Semaphore` hay quota application.

## 8. Demo #2 — gửi body dở, chiếm slot và chứng minh cleanup

Demo này dùng **một protocol binary nhỏ tự định nghĩa**, **không phải HTTP**. Frame của nó:

~~~text
+--------------------------------+--------------------------+
| 4-byte signed int length       | body bytes (length N)    |
+--------------------------------+--------------------------+
  DataOutputStream.writeInt         N bytes
~~~

Server có:

- **BODY_LIMIT=16 bytes**: kiểm tra length trước khi `readNBytes(length)`, tránh allocate size vô hạn.
- **IDLE_MS=300 ms**: accepted socket đặt read timeout.
- **Semaphore(1)**: tối đa một request/frame đang được xử lý.
- `ExecutorService` cố định và một acceptor thread riêng; không tạo unbounded worker per connection.
- `CountDownLatch` để thứ tự test **không phụ thuộc may rủi lịch chạy thread**.

Bốn kết nối tuần tự/tương tác có chủ đích:

1. Slow client gửi `length=8`, chỉ gửi 2 bytes `AB` rồi dừng: **giữ một slot**; server chờ các body bytes còn thiếu.
2. Client thứ hai kết nối khi slot vẫn bị giữ: server **từ chối ngay với `BUSY`**.
3. Sau khi slow client bị read timeout và slot được release, client mới khai báo `length=99`: server kiểm tra 99 vượt BODY_LIMIT=16 và trả **`TOO_LARGE`** trước khi allocate.
4. Client hợp lệ sau đó gửi `length=4` + `PING`: server phản hồi **`OK:PING`**. Sau completion, semaphore có lại **1 permit**.

### 8.1. Tệp đầy đủ `SlowBodyCapacityLab.java`

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class SlowBodyCapacityLab {
    static final int BODY_LIMIT = 16;
    static final int IDLE_MS = 300;

    static void sendLine(Socket peer, String message) throws IOException {
        OutputStream out = peer.getOutputStream();
        out.write((message + "\n").getBytes(StandardCharsets.US_ASCII));
        out.flush();
    }

    static String receiveLine(Socket peer) throws IOException {
        return new BufferedReader(new InputStreamReader(
                peer.getInputStream(), StandardCharsets.US_ASCII)).readLine();
    }

    static void process(Socket peer) throws IOException {
        try (peer) {
            peer.setSoTimeout(IDLE_MS);
            DataInputStream input = new DataInputStream(peer.getInputStream());
            try {
                int length = input.readInt();
                if (length < 0 || length > BODY_LIMIT) {
                    sendLine(peer, "TOO_LARGE");
                    return;
                }
                byte[] body = input.readNBytes(length);
                if (body.length != length) {
                    sendLine(peer, "TRUNCATED");
                    return;
                }
                sendLine(peer, "OK:" +
                        new String(body, StandardCharsets.US_ASCII));
            } catch (SocketTimeoutException timeout) {
                sendLine(peer, "IDLE_TIMEOUT");
            }
        }
    }

    static void serve(ServerSocket server, ExecutorService handlers,
                      Semaphore slots,
                      CountDownLatch firstSlot,
                      CountDownLatch firstDone,
                      CountDownLatch oversizedDone,
                      CountDownLatch finalDone) throws IOException {
        AtomicInteger handled = new AtomicInteger();
        for (int n = 0; n < 4; n++) {
            Socket peer = server.accept();
            if (!slots.tryAcquire()) {
                try (peer) {
                    sendLine(peer, "BUSY");
                }
                continue;
            }
            int id = handled.incrementAndGet();
            if (id == 1) firstSlot.countDown();
            handlers.execute(() -> {
                try {
                    process(peer);
                } catch (IOException error) {
                    System.err.println("Peer I/O error: " +
                            error.getClass().getSimpleName());
                } finally {
                    slots.release();
                    if (id == 1) firstDone.countDown();
                    if (id == 2) oversizedDone.countDown();
                    if (id == 3) finalDone.countDown();
                }
            });
        }
    }

    static Socket connect(int port) throws IOException {
        Socket peer = new Socket("127.0.0.1", port);
        peer.setSoTimeout(3000);
        return peer;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService acceptor = Executors.newSingleThreadExecutor();
        ExecutorService handlers = Executors.newFixedThreadPool(2);
        Semaphore slots = new Semaphore(1);
        CountDownLatch firstSlot = new CountDownLatch(1);
        CountDownLatch firstDone = new CountDownLatch(1);
        CountDownLatch oversizedDone = new CountDownLatch(1);
        CountDownLatch finalDone = new CountDownLatch(1);
        try (ServerSocket server = new ServerSocket(
                0, 4, InetAddress.getByName("127.0.0.1"))) {
            server.setSoTimeout(5000);
            Future<?> serving = acceptor.submit(() -> {
                serve(server, handlers, slots,
                        firstSlot, firstDone, oversizedDone, finalDone);
                return null;
            });
            int port = server.getLocalPort();

            try (Socket slow = connect(port)) {
                DataOutputStream output =
                        new DataOutputStream(slow.getOutputStream());
                output.writeInt(8);
                output.write("AB".getBytes(StandardCharsets.US_ASCII));
                output.flush();
                if (!firstSlot.await(3, TimeUnit.SECONDS))
                    throw new IllegalStateException("First slot not acquired");

                try (Socket extra = connect(port)) {
                    System.out.println("Concurrent extra: " +
                            receiveLine(extra));
                }
                System.out.println("Slow body: " + receiveLine(slow));
            }
            if (!firstDone.await(3, TimeUnit.SECONDS))
                throw new IllegalStateException("Slot not released");

            try (Socket tooLarge = connect(port)) {
                new DataOutputStream(tooLarge.getOutputStream()).writeInt(99);
                System.out.println("Oversize body: " +
                        receiveLine(tooLarge));
            }
            if (!oversizedDone.await(3, TimeUnit.SECONDS))
                throw new IllegalStateException("Oversize slot not released");

            try (Socket healthy = connect(port)) {
                DataOutputStream out =
                        new DataOutputStream(healthy.getOutputStream());
                out.writeInt(4);
                out.write("PING".getBytes(StandardCharsets.US_ASCII));
                System.out.println("Recovered slot: " +
                        receiveLine(healthy));
            }
            if (!finalDone.await(3, TimeUnit.SECONDS))
                throw new IllegalStateException("Final slot not released");
            serving.get(3, TimeUnit.SECONDS);
            System.out.println("Active slots after requests: " +
                    slots.availablePermits());
        } finally {
            acceptor.shutdownNow();
            handlers.shutdownNow();
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 SlowBodyCapacityLab.java
java SlowBodyCapacityLab
~~~

**Stdout đã kiểm chứng với `--release 17`:**

~~~text
Concurrent extra: BUSY
Slow body: IDLE_TIMEOUT
Oversize body: TOO_LARGE
Recovered slot: OK:PING
Active slots after requests: 1
~~~

### 8.2. Vì sao `Concurrent extra: BUSY`?

- Slow client đã kết nối, acceptor `slots.tryAcquire()` thành công.
- `firstSlot.countDown()` báo cho main rằng permit đã bị giữ.
- Main **không đóng slow client**, tiếp tục tạo second client.
- Acceptor nhận second connection nhưng `tryAcquire() == false`, nên gửi `BUSY` rồi đóng socket.
- Không có thread mới xử lý body của second client; nó không được đưa vào `handlers.execute(...)`.

Điều này minh họa **active-handler admission**. Trong hệ thống HTTP thực, response overload có thể là 503, 429, hoặc immediate close tùy contract, nhưng **`BUSY` ở đây là dòng text của protocol lab**, không phải HTTP status.

### 8.3. Vì sao `Slow body: IDLE_TIMEOUT`?

- First client khai báo body length 8 nhưng chỉ gửi `AB` (2 bytes).
- Server đã đọc đủ 4-byte prefix, xác nhận length <=16, rồi gọi `readNBytes(8)`.
- Khi không có thêm bytes suốt `IDLE_MS=300`, blocking read ném `SocketTimeoutException`.
- Code trả `IDLE_TIMEOUT` và try-with-resources đóng accepted socket.
- `finally` giải phóng `slots.release()` rồi đánh dấu `firstDone`.

Nếu peer chủ động đóng connection trước khi gửi đủ 8 bytes, `readNBytes(8)` có thể trả **ít hơn 8** và code trả `TRUNCATED`; không nhầm EOF với timeout.

### 8.4. Vì sao `Oversize body: TOO_LARGE`?

- Client khai báo length 99 trong 4-byte prefix, **không gửi body**.
- Server so sánh `length > BODY_LIMIT=16` trước khi gọi `readNBytes(length)`.
- Nó từ chối ngay với `TOO_LARGE` và đóng socket, không allocate buffer 99 bytes vì tin client.

Trong HTTP thật, `Content-Length` có thể vắng mặt, giả mạo, quá lớn hoặc dùng chunked framing. Nên kiểm tra **số bytes thực nhận** và giới hạn sau giải nén khi có compression; không đủ nếu chỉ check một con số do client khai báo.

### 8.5. Vì sao `Recovered slot: OK:PING`?

- Client thứ ba sau khi slow client timeout vẫn chạy bình thường; nó bị reject vì body length 99, nhưng slot được release.
- Client thứ tư khai báo body 4 bytes và gửi chính xác `PING`.
- Server có permit trống nên xử lý frame, trả `OK:PING`.
- `finalDone` chờ đến khi task đã thực thi `slots.release()`; cuối chương trình ghi `Active slots after requests: 1`.

Điều quan trọng không chỉ là server biết **từ chối** request xấu, mà còn **phục hồi capacity và tiếp tục phục vụ request tốt**. Nếu timeout branch quên release permit hoặc quên close socket, đến request tốt sau đó có thể bị BUSY mãi.

### 8.6. Giới hạn của lab protocol

Code cố ý không implement HTTP/TLS, authentication, global memory accounting, fair queues hoặc pressure khi số connections rất lớn. Nó chỉ xử lý 4 accepted sockets để minh họa cơ chế. Đặc biệt, vì permit được giữ từ **acceptor trước khi dispatch**, worker queue của handler pool không tự sinh backlog cho các connection đang bị reject trong ví dụ. Production vẫn cần kiểm soát **executor rejection** (ví dụ `RejectedExecutionException` khi shutdown/bounded queue đầy), đóng socket và release permit đúng một lần. Không copy fixture thành server Internet.

## 9. Các tầng timeout trong Java 17

### 9.1. `ServerSocket.setSoTimeout`: chờ kết nối mới

~~~java
try (ServerSocket listener =
             new ServerSocket(0, 16, InetAddress.getByName("127.0.0.1"))) {
    listener.setSoTimeout(2000);
    Socket accepted = listener.accept(); // Có thể SocketTimeoutException.
}
~~~

Đây là **mảnh code**, imports `ServerSocket`, `Socket`, `InetAddress`; nó chưa cleanup `accepted` nếu có thành công, nên cần close socket ở code thực. `setSoTimeout(2000)` áp dụng **chỉ cho `accept()`**, không phải body read sau accept.

### 9.2. `Socket.setSoTimeout`: chờ dữ liệu của accepted socket

~~~java
Socket accepted = listener.accept();
accepted.setSoTimeout(2000);
int nextByte = accepted.getInputStream().read();
~~~

Mảnh code. `SocketTimeoutException` phát sinh nếu blocking `read()` không có dữ liệu trong khoảng chờ, socket vẫn hợp lệ theo API. Application thường chọn return error/close vì request không tiến triển, nhưng hành động đóng là **chính sách của bạn**, không phải `setSoTimeout` đã tự đóng.

### 9.3. Total deadline bằng monotonic time

~~~java
long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
while (!requestComplete) {
    long remaining = deadline - System.nanoTime();
    if (remaining <= 0) {
        // total timeout: ngừng nhận request và cleanup.
        break;
    }
    socket.setSoTimeout((int)Math.max(1, Math.min(2000,
            TimeUnit.NANOSECONDS.toMillis(remaining))));
    // InputStream.read(); cập nhật tiến độ/byte budget.
}
~~~

Đây là **mảnh code** có `socket`/`requestComplete` do ứng dụng định nghĩa. Với deadline lớn, tránh cast long→int overflow; sử dụng clamp/cap như ví dụ. `System.nanoTime()` không phải thời gian epoch; chỉ dùng để đo duration/difference.

Trong chương trình #1, deadline 650 ms được chọn cho bài test; ở production phải tính cả thiết bị và độ trễ mạng hợp lệ, ví dụ upload file lớn không thể có một total deadline ngắn như request GET không body.

### 9.4. Phân biệt timeout với EOF và IOException

| Quan sát | Ý nghĩa cơ bản |
| --- | --- |
| `InputStream.read() == -1` | Peer đã gửi EOF cho chiều đọc, không nhất thiết timeout |
| `SocketTimeoutException` | Lời gọi blocking read vượt `SO_TIMEOUT` |
| `SocketException: Connection reset` | Transport bị reset/đóng bất thường |
| `EOFException` từ `DataInputStream.readInt()` | Chưa đủ bytes cho prefix 4-byte |
| `Future.get(timeout)` timeout | Task không kết thúc trước hạn tại caller; **không tự cancel task** |
| `ServerSocket.accept()` timeout | Không có connection được accept trước `SO_TIMEOUT` |
| `SocketChannel.read` trả `0` ở nonblocking | Tạm chưa có bytes, **không** phải EOF hay socket timeout |
| App total deadline quá hạn | Policy do ứng dụng áp trên toàn phase |

**Timeout không luôn có cùng HTTP status.** Khi connection mới chỉ gửi vài bytes, parser có thể không xác định nổi request hợp lệ để trả status; đóng socket đôi khi là lựa chọn hợp lý. Khi application đã có request context và còn output channel, có thể trả 408/413/431/503 theo quy ước phù hợp.

## 10. Java HttpServer của JDK và các property liên quan

Nếu hệ thống dùng `com.sun.net.httpserver.HttpServer`, handler thường chỉ được gọi **sau khi HTTP headers đã được server parse**. Một client gửi headers rất chậm có thể chiếm tài nguyên **trước khi `HttpHandler.handle(exchange)` chạy**, nên giới hạn trong handler chưa đủ.

Tài liệu Oracle **Java SE 17 — Java Networking** có mục **HTTP Server Properties** cho implementation mặc định của module `jdk.httpserver`:

| Property (JDK-specific) | Mục đích | Điểm cần lưu ý |
| --- | --- | --- |
| `jdk.httpserver.maxConnections` | Giới hạn số open connections (gồm active và idle) | Không phải cùng nghĩa handler concurrency |
| `sun.net.httpserver.maxReqHeaders` | Giới hạn số request header fields | Server có thể terminate request nếu quá |
| `sun.net.httpserver.maxReqHeaderSize` | Giới hạn kích cỡ request header section | Không đồng nghĩa body size |
| `sun.net.httpserver.maxReqTime` | Thời gian cho phép nhận request headers và body | Tài liệu Java17 mô tả giá trị bằng **mili-giây** và độ chính xác implementation-specific |
| `sun.net.httpserver.maxRspTime` | Giới hạn thời gian gửi response | Bảo vệ một phần slow receiver/output |
| `sun.net.httpserver.idleInterval` | Giới hạn thời gian giữ connection idle | Khác total request deadline |
| `sun.net.httpserver.maxIdleConnections` | Số idle connections được giữ | Không thay active connection limit |
| `sun.net.httpserver.drainAmount` | Số unread request body bytes tự drain để reuse connection | Đóng sớm có thể ảnh hưởng keepalive |

**Quan trọng:** các properties trên là **chi tiết implementation của JDK**, không phải mọi HTTP framework/vendor Java đều hiểu giống nhau. Giá trị mặc định và cách áp dụng cần xác minh theo đúng **JDK 17 update/runtime đang chạy**. Khi thử, dùng **một process riêng** hoặc cài JVM options từ lúc khởi động, không đổi global properties bừa giữa nhiều requests.

Ví dụ cấu hình minh họa (không phải lệnh cho lab raw TCP phía trên):

~~~bash
java -Dsun.net.httpserver.maxReqTime=5000 -Dsun.net.httpserver.maxReqHeaderSize=8192 -Djdk.httpserver.maxConnections=100 -cp app.jar Main
~~~

**Đây là ví dụ JVM flags có tên class/jar minh họa**, không chạy được nếu chưa có `app.jar` và `Main`. Số `5000` là 5 giây theo tài liệu property (không phải 5000 giây). Không suy rằng server `HttpServer` sẽ trả **408**; tài liệu mô tả việc **terminate connection** hoặc handler nhận `IOException` tùy phase. Việc property đang có tác dụng phải được kiểm chứng bằng test chậm thực tế và metrics.

### 10.1. Vì sao vẫn cần giới hạn trong handler?

Giới hạn HTTP parser/header không chặn:

- Body rất lớn trong endpoint upload nếu application tự đọc mà không có quota.
- Parser JSON/XML có nesting/CPU amplification.
- Business handler chờ database lâu.
- Large decompressed body dù raw compressed bytes ít.
- Quá nhiều cùng lúc vào một downstream dependency.
- Unbounded asynchronous task queues sau khi headers đã parse.

Ngược lại, handler-level body check **không** bảo vệ đoạn **trước khi handler được dispatch**. Một thiết kế tốt áp nhiều tầng giới hạn đúng trách nhiệm.

## 11. Active connection cap và executor queue

Một server có thể dùng:

~~~java
Semaphore slots = new Semaphore(64);
if (!slots.tryAcquire()) {
    // Không đưa socket vào unbounded queue.
    // Reject/close sớm theo protocol.
    return;
}
try {
    // Xử lý connection/request đang có slot.
} finally {
    slots.release();
}
~~~

Đây là **mảnh code** cần đồng bộ với lifecycle của accepted socket. Nếu đã acquire slot nhưng `ExecutorService.execute(...)` ném `RejectedExecutionException`, code phải close socket và release slot; **không** để permit bị mất.

### 11.1. Bounded worker pool thôi chưa đủ

`Executors.newFixedThreadPool(n)` dùng n threads, nhưng mặc định task queue bên trong có thể **không có giới hạn thực tế phù hợp**. Nếu acceptor liên tục submit tasks cho slow clients, số pending tasks có thể tăng mạnh dù n workers cố định.

Production nên áp:

- Connection admission trước khi enqueue, hoặc `ThreadPoolExecutor` với **bounded BlockingQueue**.
- Rejection handler rõ ràng: close/503/429 tùy protocol và trạng thái.
- Pool size có cơ sở từ blocking workload, không tăng tùy ý theo số clients.
- Per-IP/per-tenant quotas khi thích hợp, không chỉ global.
- Global file descriptor/socket budgets và TLS handshake caps.
- Graceful shutdown: stop accepting → dừng tasks chờ → đóng/draint active sockets → release permits.

### 11.2. Semaphore không giới hạn resource trước `accept`

Một accepted TCP socket đã có kernel/FD cost **trước khi application acquire slot**. Nếu quá nhiều connections pending, cần enforcement ở **listener/OS/proxy/TLS/gateway** chứ không chỉ semaphore trong code handler. Trong demo, mỗi test chỉ có tối đa hai kết nối cùng thời điểm nên chúng ta không thử exhaustion thật.

## 12. Header timeout không thay body timeout

Một HTTP client có thể hoàn thành headers ngay:

~~~http
POST /upload HTTP/1.1
Host: localhost
Content-Length: 100000

~~~

rồi gửi body rất chậm. Header total deadline đã được thỏa mãn, nhưng server vẫn có nguy cơ giữ request body stream lâu. Cần thiết kế body timeout theo:

1. **Maximum body bytes**: không allocate theo client-supplied length nếu chưa validate; đếm bytes thực.
2. **Idle gap**: nếu không có byte mới trong một khoảng, cancel upload.
3. **Total upload deadline**: tính theo thời gian hợp lý với kích thước, băng thông tối thiểu và policy.
4. **Minimum sustained data rate**: nên đo qua cửa sổ đủ dài để chịu burst/jitter, không phạt một pause ngắn hợp lệ.
5. **Deadline downstream**: xử lý database/disk có thể chậm độc lập với network.
6. **Cleanup**: xóa temporary files chưa hoàn tất, release file descriptors và request slot khi upload thất bại.

### 12.1. Bounded read pattern

~~~java
int maxBody = 1024 * 1024;
byte[] data = requestInput.readNBytes(maxBody + 1);
if (data.length > maxBody) {
    // Quá giới hạn: reject/close theo HTTP protocol và policy.
}
~~~

Đây là mảnh code, `requestInput` chưa khai báo. `readNBytes` giới hạn số bytes đọc vào RAM trong thao tác này, **không** thay total read deadline; chờ dữ liệu vẫn có thể block theo InputStream. Với upload lớn, nên stream vào sink có quota và cleanup thay vì giữ toàn bộ trong heap.

### 12.2. Số bytes nhận được phải quan sát thật

Các client có thể:

- Khai báo `Content-Length` sai hoặc thiếu.
- Dùng chunked transfer encoding.
- Gửi body từng phần rồi gửi EOF.
- Gửi compressed payload khiến decoded size lớn.
- Gửi bytes nhanh ban đầu rồi dừng hoàn toàn.
- Gửi mỗi đợt vừa đủ để không vượt idle timeout nhưng tổng request kéo dài vô lý.

Không test mỗi case “body hoàn chỉnh nhanh”. Kết hợp **incomplete**, **oversized**, **trickle**, **abrupt close**, và **valid request ngay sau các failure cases**.

## 13. Tại sao không chỉ tăng thread pool và timeout?

Một cách xử lý sai thường thấy:

~~~text
Hiện tại có 100 slow clients, 100 threads bị block.
→ Tăng pool từ 100 lên 1000 threads.
→ Mỗi thread thêm stack/CPU overhead.
→ Chỉ một lần surge có 1000 slow clients là lại hết.
~~~

Tăng capacity có thể hữu ích nếu workload hợp lệ đòi nhiều concurrency, nhưng không thay **thời gian tối đa một resource có thể bị giữ**, **admission policy**, **quota bytes** hay **bounded queue**. Hệ thống cần xác định **SLO** (ví dụ header phải xong trong X giây ở đa số clients), và quan sát p95/p99 trước khi đặt giới hạn.

### 13.1. Giới hạn công bằng cho client mạng yếu

Một absolute deadline quá ngắn có thể từ chối người dùng legitimate trên mạng di động. Vì vậy:

- Chọn deadline theo endpoint: GET nhẹ khác upload file.
- Có resume upload/chunked resumable protocol nếu file lớn và mạng chập chờn.
- Có body rate floor theo cửa sổ hợp lý; không phạt một jitter spike.
- Tách early header deadline ngắn hơn total body deadline khi phù hợp.
- Ưu tiên 429/503 có `Retry-After` theo contract khi overload server, không giả là request timeout.
- Không ép người dùng retry command có side effects nếu không có idempotency key.
- Dùng gateway/reverse proxy để xử lý connection admission và TLS policy hợp pháp.

## 14. Kiểm chứng qua metrics, không chỉ thông báo lỗi

| Metric | Nó đo gì? | Khi test chậm, kỳ vọng |
| --- | --- | --- |
| `accepted_connections_total` | Số accepted TCP sockets | Tăng tương ứng 4 test cases |
| `active_connections` | Connections chưa close | Trở về baseline sau test |
| `active_handlers` | Tasks xử lý có slot | Không vượt cap |
| `handler_queue_depth` | Tasks chờ executor | Không tăng vô hạn |
| `request_header_bytes` | Số bytes header đã đọc | Không vượt max header budget |
| `request_body_bytes` | Bytes body đã đọc | Max enforced |
| `request_header_duration_ms` | Thời gian header parsing | Trickle gần total deadline |
| `request_body_duration_ms` | Thời gian đọc body | Slow-body timeout |
| `idle_read_timeout_total` | Read gap timeout | Tăng ở case IDLE |
| `request_total_timeout_total` | Absolute request deadline | Tăng ở case TRICKLE |
| `header_limit_rejected_total` | Headers quá cỡ | Tăng ở case OVERSIZE |
| `body_limit_rejected_total` | Declared/actual body quá cỡ | Tăng ở case size 99 |
| `capacity_rejected_total` | Không lấy được permit | Tăng khi slot đang bận |
| `resource_release_failures` | Permit/FD leak được phát hiện | **0** |
| `connection_close_reason` | Lý do đóng/cancel | Phân biệt timeout/EOF/size/policy |

Không dùng raw credentials, API keys, full URL query hoặc request body làm log/metric label. Có thể log **case ID/test run ID**, reason và aggregate dimensions an toàn. Trong test server nhỏ, nhãn `IDLE_TIMEOUT`/`TOTAL_TIMEOUT` là kết quả chính xác hơn chỉ ghi chung `IOException`.

### 14.1. Phân tích kết quả theo phase

~~~text
Client kết nối được?
    |
    +-- Không: DNS/connect/refused, chưa test HTTP timeout.
    |
    +-- Có, server nhận request headers đầy đủ?
            |
            +-- Không:
            |      +-- idle gap timeout? -> IDLE
            |      +-- absolute age over? -> TOTAL
            |      +-- header bytes > cap? -> HEADER_LIMIT
            |
            +-- Có: body đã đủ chưa?
                   |
                   +-- Không:
                   |      +-- body read timeout
                   |      +-- body size/quota reject
                   |      +-- EOF/incomplete
                   |
                   +-- Có: handler có slot và xử lý đúng hạn?
                          |
                          +-- Busy -> 429/503/close theo policy
                          +-- Completed -> response normal
~~~

**Một HTTP status 408 không cho biết một mình nguyên nhân**. Muốn phân biệt idle-gap timeout với overall deadline phải có trace phase metrics/server logs; một số stack sẽ đóng socket không gửi status.

## 15. Thử nghiệm thực tế nên lập kế hoạch như thế nào?

| Test | Client gửi | Cơ chế bạn kiểm chứng | Điều cần đo |
| --- | --- | --- | --- |
| Fast baseline | Headers/body đầy đủ ngay | Không false reject | 200/normal response |
| Header idle | `GET /` rồi dừng | `Socket.setSoTimeout` | Idle counter, close |
| Header trickle | Một byte mỗi khoảng nhỏ hơn idle cap | Total deadline | Total timeout, không giữ vô hạn |
| Header oversize | Tối đa +1 byte chưa kết thúc headers | Header byte cap | Reject/close, no buffer growth |
| Many header fields | N fields vượt configured cap | Header count limit | No parser blowup |
| Header complete/body absent | Content-Length >0 nhưng không gửi body | Body idle timeout | Cleanup, no stuck worker |
| Body trickle | Body từng byte nhỏ | Body total/min-rate | Deadline/limited throughput |
| Oversized declared body | Length prefix/Content-Length >limit | Early size rejection | No huge allocation |
| Actual bytes exceed limit | Declared thiếu/sai hoặc streaming | Byte counting | Cap thực nhận |
| Incomplete frame EOF | Đóng output sớm | Phân biệt EOF/timeout | TRUNCATED/400 |
| Active cap reached | Second connection trong khi first chiếm slot | Semaphore/admission | BUSY/503/close, no leaked slot |
| Valid after timeout | Retry request hợp lệ sau cleanup | Capacity restored | Success |
| Slow response reader | Client không đọc response | Write timeout/buffers | Không nhầm với slow sender |
| TLS slow handshake | Client gửi TLS ClientHello chậm | Handshake deadline | Kết nối không bị giữ vô hạn |
| HTTP/2 stream stall | Một stream gửi body chậm | Stream flow control/deadline | Không làm nghẽn mọi streams |
| Graceful stop during slow request | Stop server | Shutdown/cancel | Không leak threads/sockets |
| Deadline under CPU load | Server bị GC/scheduler pause | False positives | Chọn guardrails hợp lý |

**Không cần chạy hàng nghìn slow clients** để chứng minh policy logic. Hai demos dùng đúng vài sockets và đồng bộ; load test với nhiều kết nối chỉ nên thực hiện trong staging có quyền, kèm resource budget và khả năng rollback.

## 16. Các sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chỉ có `setSoTimeout` cho read | Trickle bytes có thể reset idle timer | Total deadline + idle gap |
| Cho `ServerSocket.setSoTimeout` bảo vệ request body | Nó chỉ timeout `accept()` | Set trên accepted Socket và app deadline |
| Set read timeout rồi tin write cũng timeout | `SO_TIMEOUT` áp read, không phải write | Write timeout/close policy riêng |
| Không có header max bytes | Tiny slow send giữ parser và memory | Header bytes/count cap |
| Check `Content-Length` nhưng không đếm actual body | Chunked/malformed payload vượt quota | Bounded streaming |
| Allocate array theo declared length từ client | Có thể memory exhaustion | Validate length trước allocate |
| Bị timeout nhưng không close socket | Giữ FD/connection state | Try-with-resources/finally |
| Acquire semaphore mà quên release khi exception | Slot leak vĩnh viễn | Release once in finally |
| Chỉ giới hạn handler threads, accept không hạn chế | Pre-handler connections giữ resource | Listener/TLS/proxy caps |
| Unbounded executor queue | Slow clients sinh pending tasks vô hạn | Bounded admission/task queue |
| Dùng `Thread.sleep` trong server handler để “timeout” | Chặn thread, không đo network phase | Deadline + timed I/O |
| Không xử lý EOF riêng | Đánh đồng client đóng với timeout | Check `read()==-1`/`EOFException` |
| Gửi lỗi HTTP khi chưa có request hợp lệ bằng mọi giá | Socket có thể đã đóng, parser state thiếu | Close khi không thể response an toàn |
| Giả sử mỗi `write(1)` là một TCP packet | TCP byte stream, Nagle/OS batching | Đo bytes/timestamps ở server |
| Dùng mốc wall-clock cho deadline | NTP/time changes | Monotonic elapsed time |
| Tự scale demo lên nhiều host không cho phép | Có thể gây mất dịch vụ | Loopback/staging với quyền |
| Chỉ test reject mà không test success sau reject | Có thể leak permits/FDs | Valid-after-timeout test |
| Chọn timeout 250 ms cho production mobile | Dễ false-positive | SLO, p99, network conditions |
| Tăng pool size vô hạn | Tài nguyên vẫn có giới hạn | Caps và pressure policy |
| Đọc toàn bộ upload vào heap | OOM hoặc GC pressure | Streaming quotas và cleanup |
| Không dùng `Future.get(timeout)` trong integration test | Bài test có thể treo mãi | Bounded waits, cancel/close |
| Coi `Future.get(timeout)` tự cancel task | Task vẫn tiếp tục khi get timeout | Cancel/close đúng ownership |
| Nhầm 408 với 503 | Client gửi request chậm vs server quá tải | Tách nguyên nhân theo phase |
| Coi header parser demo là HTTP server production | Thiếu framing/auth/chunking/HTTP semantics | Dùng server/framework được duy trì |
| Log raw HTTP Authorization/body | Lộ dữ liệu nhạy cảm | Redaction/aggregate metrics |

## 17. Bài tập có đáp án

### Bài 1 — Header từng byte

Server đặt `Socket.setSoTimeout(250)`, client gửi 1 byte mỗi 100 ms suốt 60 giây. Có chắc server timeout sau 250 ms?

**Đáp án:** Không. Nếu mỗi blocking `read()` nhận được byte mới trước 250 ms, idle timeout không phát sinh. Cần **total header deadline**, min sustained rate hoặc tổng policy tương tự.

### Bài 2 — Accept timeout

Server listener gọi `server.setSoTimeout(1000)` rồi accept được client. Nó có quyền mặc nhiên đợi tối đa 1 giây cho request body không?

**Đáp án:** Không. Timeout của `ServerSocket.accept()` là riêng. Phải set read timeout trên accepted `Socket` và/hoặc application total deadline.

### Bài 3 — Vì sao dùng `nanoTime`?

**Đáp án:** `System.nanoTime()` phù hợp để tính elapsed durations; `System.currentTimeMillis()` là wall-clock có thể bị chỉnh đồng hồ. Dùng hiệu hai mốc monotonic để so deadline.

### Bài 4 — Request chưa đủ headers

Client gửi `GET /` rồi chờ, không đóng connection. Sau read timeout, server xử lý gì?

**Đáp án:** Có thể trả 408 nếu còn output an toàn và server policy hỗ trợ, rồi close; cũng có thể đóng không trả response. Bắt `SocketTimeoutException`, giải phóng tài nguyên, không giữ request mãi.

### Bài 5 — Đọc body đã khai báo 1 GiB

Một client gửi length prefix 1 GiB tới server có body limit 16 bytes. Có nên `new byte[1_073_741_824]` để đọc rồi kiểm tra?

**Đáp án:** Không. Kiểm tra length trước allocate; trả reject/close ngay. Với HTTP streaming, còn phải đếm actual received bytes.

### Bài 6 — BUSY và Semaphore

Demo #2 giữ `Semaphore(1)` trong slow handler, client thứ hai đến. Kết quả mong đợi?

**Đáp án:** `slots.tryAcquire() == false`, client thứ hai nhận `BUSY` và socket đóng; không tạo task xử lý body cho nó. Trong HTTP production có thể dùng 503/429 hoặc close theo overload policy.

### Bài 7 — Vì sao kiểm tra tiếp request hợp lệ?

**Đáp án:** Để chứng minh sau timeout/reject, server không leak permit/socket/worker. Nếu không, server có thể trông như từ chối đúng nhưng capacity giảm dần về 0.

### Bài 8 — Slow sender hay slow receiver?

Client gửi request body chậm: server đang bị giữ ở read hay write? Client đọc response cực chậm: server bị giữ ở đâu?

**Đáp án:** Trường hợp đầu: **server read path**. Trường hợp sau: **server write path**. Cần deadline và resource accounting riêng.

### Bài 9 — Có nên chỉ tăng ThreadPoolExecutor?

**Đáp án:** Không. Nhiều slow clients vẫn có thể giữ toàn bộ workers và unbounded task queue. Cần admission, per-connection deadline, bounded queue, global cap và cleanup.

### Bài 10 — Trickle có bị idle timeout không?

Trong demo #1, mỗi byte cách 90 ms, idle limit 250 ms. Vì sao cuối cùng vẫn nhận 408?

**Đáp án:** Do **total deadline 650 ms**, không phải idle-gap. Headers vẫn chưa có CRLFCRLF khi deadline hết.

### Bài 11 — Header size và body size

Một request có 30 bytes headers và 10 MiB body, header cap 64 bytes. Header cap đã bảo vệ toàn bộ memory chưa?

**Đáp án:** Chưa. Body có budget riêng; phải giới hạn actual body bytes, rate/deadline và streaming memory/disk.

### Bài 12 — Socket timeout có tự đóng socket?

Sau `SocketTimeoutException` do `setSoTimeout`, accepted socket có tự động closed không?

**Đáp án:** Theo API, socket vẫn có thể hợp lệ. Server phải quyết định retry read hay close; lab chọn trả timeout rồi try-with-resources đóng để giải phóng.

### Bài 13 — Retry khi upload timeout

Client gửi upload có side-effect rồi mất kết nối giữa chừng. Có an toàn để retry ngay không?

**Đáp án:** Không thể tự kết luận server chưa xử lý phần nào. Với nghiệp vụ cần tính nhất quán, dùng idempotency key, atomic finalize/commit, resumable upload IDs hoặc trạng thái job để tránh trùng.

### Bài 14 — Dùng raw Socket thay HttpClient vì sao?

**Đáp án:** Raw Socket cho phép cố ý dừng giữa request line/header và gửi từng byte đúng timing. `HttpClient` bình thường che bớt cơ chế HTTP formatting, phù hợp API business nhưng không thuận tiện cho header-level fault injection có kiểm soát.

### Bài 15 — Production timeout bao nhiêu là đủ?

**Đáp án:** Không có con số phổ quát. Cần dựa trên endpoint type, kích thước upload, mạng mobile, SLO, proxy/infra behavior, p95/p99 và false positive rate. Giá trị vài trăm ms trong demo chỉ để thử cục bộ.

## 18. Checklist trước khi hoàn thành lab

- [ ] Đã xác định đúng slow sender vs slow receiver.
- [ ] Chỉ chạy thí nghiệm trên loopback hoặc staging có quyền.
- [ ] Server dùng cổng 0 và timeout hữu hạn để tránh test treo.
- [ ] Đã tạo client gửi nhanh làm baseline.
- [ ] Đã tạo client gửi vài byte rồi dừng nhưng không đóng ngay.
- [ ] Đã tạo client trickle với khoảng giữa bytes nhỏ hơn idle timeout.
- [ ] Đã đo **idle read timeout** và **total header deadline** riêng.
- [ ] Đã kiểm tra byte cap trước allocate và phân biệt header/body caps.
- [ ] Đã xác minh `ServerSocket.accept` và accepted `Socket.read` có timeout khác nhau.
- [ ] Đã kiểm tra EOF/SocketTimeoutException/SocketException thành các nguyên nhân riêng.
- [ ] Đã áp active handler/connection cap và bounded worker queue policy.
- [ ] Đã chứng minh reject quá tải **không** giữ slot mới.
- [ ] Đã chứng minh timeout/error **release slot và close socket**.
- [ ] Đã gửi một request hợp lệ sau các case lỗi và thấy server xử lý bình thường.
- [ ] Đã đo active_connections, active_handlers, header/body bytes, reject/timeout totals.
- [ ] Đã xem xét độ trễ hợp lệ của thiết bị mobile và tránh chọn deadline quá ngắn.
- [ ] Đã bảo đảm unit/integration test có bounded awaits và cleanup trong finally.
- [ ] Đã phân biệt testcase raw TCP fixture với HTTP server production.
- [ ] Không dùng test để gửi traffic chậm hàng loạt tới dịch vụ bên ngoài.
- [ ] Hai chương trình Java biên dịch bằng `javac --release 17` và stdout đã được đối chiếu.

## 19. Tài liệu tham khảo

- [Java SE 17 — ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): `accept()`, `setSoTimeout` cho accept wait, backlog và lifecycle.
- [Java SE 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): `setSoTimeout` cho blocking input read, socket options và close.
- [Java SE 17 — SocketTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketTimeoutException.html): timeout trên socket operation.
- [Java SE 17 — DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readInt()` cho length-prefix.
- [Java SE 17 — InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): `readNBytes` và EOF handling.
- [Java SE 17 — Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html): active resource permits và release.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): đồng bộ deterministic test.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): worker ownership, shutdown.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get(timeout)` và cancellation.
- [Java SE 17 — System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): elapsed-time measurement.
- [Oracle Java SE 17 — Java Networking / HTTP Server Properties](https://docs.oracle.com/en/java/javase/17/core/java-networking.html): `sun.net.httpserver.maxReqTime`, max header, max connections, idle interval, implementation-specific behavior.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): JDK embedded HTTP server, executor/contexts/lifecycle.
- [Java SE 17 — HttpHandler](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): handler được dispatch sau HTTP parsing.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): request status 408/413/431/503, HTTP semantics.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): request line, header section, message framing và limits.

**Kết luận:** để kiểm chứng khả năng chịu **máy khách gửi chậm**, đừng chỉ cài một `read timeout`. Hãy xây các client case **nhanh, ngừng giữa request, nhỏ giọt liên tục và quá cỡ**; quan sát rõ **idle timeout, absolute deadline, header/body byte caps, active handler cap và cleanup**. Hai ví dụ Java 17 chứng minh rằng một server có thể **phát hiện request kéo dài**, **từ chối request quá giới hạn** và **phục hồi capacity để phục vụ request hợp lệ tiếp theo** mà không cần tạo tải lớn hay ảnh hưởng hệ thống bên ngoài.
