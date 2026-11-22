# Tạo TCP echo client/server trên loopback với cổng do hệ điều hành cấp

## 1. Mục tiêu và sản phẩm của bài thực nghiệm

Bài thực hành này sử dụng **Java 17+**, thư viện chuẩn `java.net` và kết nối **TCP** để tạo một **echo server** (server trả lại dữ liệu đã nhận) cùng **echo client** ngay trên một máy. Server chỉ lắng nghe **loopback IPv4 `127.0.0.1`** và yêu cầu hệ điều hành cấp một **cổng tạm (ephemeral port)** bằng cách bind vào cổng `0`. Client không biết trước số cổng: nó lấy **cổng thực tế từ `ServerSocket.getLocalPort()`**, sau đó kết nối, gửi dữ liệu và kiểm tra chính xác dữ liệu echo.

Kết quả học tập cụ thể:

1. Biết **`ServerSocket` khác `Socket`** thế nào; biết bind, accept, connect và đọc/ghi stream ở đúng phía.
2. Tạo server **không hard-code port**, tránh xung đột cổng khi nhiều bài test chạy song song; kết nối bằng cùng IPv4 loopback và port vừa được cấp.
3. Xây dựng giao thức **mỗi dòng UTF-8 là một thông điệp**: client gửi ba dòng, server nhận rồi trả `ECHO:...`.
4. Dùng `flush()`, `Socket.shutdownOutput()` và vòng lặp đọc cho đến **EOF** để kết thúc phiên echo có thứ tự mà không bị treo vì hai phía cùng chờ nhau.
5. Dùng `InputStream` và `OutputStream` để echo **byte nhị phân**, giải thích vì sao một lần `read(byte[])` **không tương ứng** một lần `write(byte[])`.
6. Áp dụng connect/read/accept timeouts, `try-with-resources` và cleanup worker thread, đồng thời phân biệt ví dụ loopback với hệ thống mạng cần bảo mật thực tế.

Hai chương trình chạy độc lập trong bài:

- `TcpEchoLinesDemo.java`: echo ba dòng văn bản Unicode, minh họa cổng `0` được OS cấp và EOF khi half-close.
- `TcpEchoBytesDemo.java`: echo bảy byte thô, bao gồm `0x00` và `0xFF`, dùng buffer nhỏ để chứng minh phải xử lý đúng số byte từng lần đọc.

Cả hai chương trình **tự khởi chạy server và client trong cùng JVM**, không cần kết nối Internet, không cần framework hoặc thư viện ngoài JDK. Chúng được thiết kế cho **một client mỗi lượt chạy**, không phải một TCP service production.

## 2. Sơ đồ đường đi của dữ liệu

~~~text
                     cùng máy / loopback IPv4
                  127.0.0.1 (không ra Internet)

 SERVER                                      CLIENT
 ServerSocket(port=0)                        Socket()
      |                                         |
      | OS cấp cổng thực P > 0                   |
      |                                         |
      |<----- connect(127.0.0.1:P) --------------|
      | accept() trả Socket peer                 |
      |                                         |
      |<------- bytes / lines -------------------|
      | đọc qua peer.getInputStream()            |
      |                                         |
      |------- echo bytes / lines -------------> |
      | ghi qua peer.getOutputStream()           |
      |                                         |
      |<------- FIN khi client.shutdownOutput() -|
      | thấy EOF ở chiều client -> server        |
      | đóng peer Socket sau khi echo            |
      |                                         |
      |--------- EOF chiều server -> client ---> |
      |                                         |
      +---- server.close()                       +-- client.close()
~~~

**`ServerSocket` là socket lắng nghe**: nó nhận kết nối mới bằng `accept()`; không dùng trực tiếp để đọc body của kết nối. **`Socket` do `accept()` trả về** là socket được dùng để đọc/ghi trao đổi TCP của client đã kết nối. Ở phía client, một đối tượng `Socket` khác gọi `connect(...)` vào địa chỉ đã bind.

**TCP là luồng byte hai chiều (full-duplex)**, không phải giao thức có sẵn “message” hoặc “line”. Server echo của bài chủ động định nghĩa **ranh giới thông điệp** bằng newline ở demo 1 hoặc chờ EOF ở demo 2; đó là quy ước **ứng dụng**, không phải TCP tự biết.

## 3. API cần dùng và vai trò chính xác

| API Java | Ở phía nào | Ý nghĩa |
| --- | --- | --- |
| `new ServerSocket(0, backlog, bindAddress)` | Server | Vừa tạo, vừa bind địa chỉ; cổng `0` cho OS chọn |
| `new ServerSocket()` + `bind(endpoint, backlog)` | Server | Tạo unbound rồi bind tường minh |
| `ServerSocket.getLocalPort()` | Server | Lấy **cổng thực tế sau bind** |
| `ServerSocket.getInetAddress()` | Server | Lấy địa chỉ local server đã bind |
| `ServerSocket.accept()` | Server | Chờ kết nối; trả `Socket` đã connect |
| `ServerSocket.setSoTimeout(ms)` | Server | Giới hạn **thời gian chờ `accept()`** |
| `new Socket()` + `connect(addr, timeout)` | Client | Kết nối TCP tới IP/port, có hạn connect |
| `Socket.getInputStream()` | Cả hai | Đọc byte từ peer |
| `Socket.getOutputStream()` | Cả hai | Gửi byte tới peer |
| `Socket.setSoTimeout(ms)` | Cả hai | Giới hạn **thời gian chờ khi đọc** (`read`) |
| `Socket.shutdownOutput()` | Client trong demo | Báo kết thúc **chiều gửi**, vẫn được đọc chiều nhận |
| `Socket.close()` | Cả hai | Giải phóng socket, đóng các luồng liên quan |
| `BufferedReader.readLine()` | Text protocol | Đọc tới newline/EOF, trả `null` khi kết thúc stream |
| `InputStream.read(byte[])` | Binary protocol | Đọc **tối đa** dung lượng buffer, trả số byte thực đọc hoặc `-1` ở EOF |

`java.net.ServerSocket` và `java.net.Socket` thuộc **`java.base`**, có sẵn trong JDK 17, không cần thêm dependencies. Mã UTF-8 dùng `java.nio.charset.StandardCharsets.UTF_8` để không phụ thuộc charset mặc định của môi trường.

## 4. Cổng 0: nhờ hệ điều hành chọn port, không phải client kết nối cổng 0

Cách bind rõ ràng nhất cho bài test:

~~~java
try (ServerSocket listener = new ServerSocket(
        0, 16, InetAddress.getByName("127.0.0.1"))) {
    int port = listener.getLocalPort(); // > 0 sau khi bind thành công
    System.out.println("port > 0: " + (port > 0));
}
~~~

*Đoạn minh họa cần imports; đây chưa phải chương trình echo đầy đủ.*

Với `new ServerSocket(0, 16, bindAddr)`:

- `0` là **tham số khi bind**, nói với hệ điều hành “chọn một cổng local còn khả dụng”. Nó **không phải cổng mà client phải dùng**.
- `16` là yêu cầu **backlog** (hàng đợi kết nối đang chờ `accept`), **không phải** số request được xử lý đồng thời, cũng không bảo đảm OS sẽ dùng đúng con số đó.
- `InetAddress.getByName("127.0.0.1")` xác định **IPv4 loopback**: server chỉ lắng nghe địa chỉ local này, thay vì tất cả interfaces.
- `listener.getLocalPort()` trả cổng đã được cấp; giá trị cụ thể **không thể đoán trước và có thể khác mỗi lần chạy**.

Một cách tương đương là tạo server chưa bind:

~~~java
try (ServerSocket listener = new ServerSocket()) {
    listener.bind(new InetSocketAddress("127.0.0.1", 0), 16);
    int port = listener.getLocalPort();
}
~~~

Ở đây `new ServerSocket()` ban đầu chưa có địa chỉ; `bind(...)` mới gắn socket với loopback và port do OS cấp. Sau khi đã bind, không gọi `bind(...)` lần thứ hai trên cùng `ServerSocket`.

**Đừng mở socket tạm để lấy một “free port”, đóng nó rồi mở lại server trên port đó.** Trong khoảng giữa hai hành động, tiến trình khác có thể chiếm cổng (*time-of-check vs time-of-use race*). Cách đúng là giữ **chính ServerSocket đã bind cổng `0`** và chuyển `getLocalPort()` cho client trong khi listener còn mở.

## 5. Loopback `127.0.0.1` khác `localhost` và `0.0.0.0`

| Giá trị | Ý nghĩa | Lựa chọn cho bài test |
| --- | --- | --- |
| `127.0.0.1` | IPv4 loopback của máy hiện tại | **Dùng cho cả server lẫn client** |
| `localhost` | Hostname, có thể resolve về IPv4 hoặc IPv6 | Hợp lệ nhưng có thể gây mismatch họ địa chỉ tùy môi trường |
| `::1` | IPv6 loopback | Chỉ dùng nếu server/client cùng IPv6, URI cần cú pháp phù hợp |
| `0.0.0.0` | Bind **mọi IPv4 interfaces** | Không dùng cho demo nếu không có lý do mở truy cập mạng ngoài |
| IP mạng LAN | Bind một interface bên ngoài loopback | Cần chính sách firewall, auth, permission thích hợp |

Khi server bind `127.0.0.1`, kết nối phải đi đến địa chỉ loopback tương ứng; không tự suy ra client từ máy khác sẽ truy cập được. Trong container, `127.0.0.1` là loopback **của namespace mạng đó**, không nhất thiết của host hoặc container khác.

Demo dùng **cùng chuỗi `"127.0.0.1"` tại cả hai đầu**, tránh một máy resolve `localhost` thành `::1` trong khi server chỉ bind IPv4. `InetAddress.getLoopbackAddress()` cũng có thể trả kiểu loopback tùy nền tảng; chọn IPv4 tường minh giúp thực nghiệm có thể tái lập.

## 6. Khi nào `accept()` bắt đầu nhận kết nối?

Server phải **bind xong trước khi client `connect`**. Sau bind, socket đã lắng nghe, nhưng `accept()` thường **chặn thread gọi** cho đến khi có kết nối.

~~~java
ServerSocket listener = new ServerSocket(
        0, 16, InetAddress.getByName("127.0.0.1"));
listener.setSoTimeout(5_000);

Socket peer = listener.accept(); // Chờ client connect.
~~~

*Đoạn minh họa có imports; cần đóng `listener` và `peer` ở cuối.*

Mỗi lần `accept()` thành công trả một **Socket của kết nối đó**, khác đối tượng `ServerSocket` đang lắng nghe. Muốn phục vụ nhiều clients, thông thường viết vòng lặp `accept()` và giao từng socket cho executor hoặc I/O event loop; bài này chỉ phục vụ **một** client để dễ quan sát.

Không được chạy tuần tự theo kiểu “gọi `accept()` rồi mới tới code `connect()` trên **cùng một thread**”, vì `accept()` sẽ đứng chờ một client chưa bao giờ được khởi phát. Hai chương trình dùng một worker thread riêng qua `ExecutorService` cho server và thread main cho client. Không cần gọi `Thread.sleep(...)`: lúc tạo worker, listener **đã bind**, nên client kết nối được dù server chưa kịp vào `accept()`; OS có thể đưa kết nối vào hàng đợi đang chờ.

`listener.setSoTimeout(5_000)` giúp `accept()` ném `SocketTimeoutException` nếu quá lâu không có kết nối. Hết timeout **không tự đóng ServerSocket**; nếu muốn tiếp tục nghe, server phải quyết định gọi `accept()` nữa. Demo đóng listener bằng `try-with-resources` sau khi chạy.

## 7. Client kết nối đến đúng cổng được OS cấp

Ở phía client:

~~~java
try (Socket client = new Socket()) {
    client.connect(new InetSocketAddress(
            "127.0.0.1", listener.getLocalPort()), 3_000);
    client.setSoTimeout(5_000);
    // client.getInputStream(), client.getOutputStream()
}
~~~

*Đoạn minh họa dùng biến `listener` từ phía server trong cùng JVM và cần imports.*

`client.connect(..., 3_000)` đặt timeout cho **thao tác kết nối**, khác timeout đọc. `client.setSoTimeout(5_000)` quy định khi một thao tác đọc trên socket chờ dữ liệu quá lâu sẽ ném `SocketTimeoutException`; đây **không phải timeout cho toàn bộ lifetime**, không hạn chế tổng số byte phải đọc và không tự đặt deadline cho mọi lần ghi.

Các sai lầm cần tránh:

- Client kết nối vào port **`0`**: sai. Port `0` chỉ có ý nghĩa để **server bind và xin OS cấp cổng**, không phải endpoint phục vụ thực.
- Client hard-code port `8080` trong khi server đã bind port `0`: hai phía dùng **hai cổng khác nhau**.
- Client dùng `localhost` giải sang IPv6 trong khi server lắng nghe `127.0.0.1` IPv4: có thể gặp `ConnectException`.
- Gọi `client.getInputStream().read()` trước khi server có dữ liệu mà không có protocol/timeouts: có thể chờ không xác định.
- Tin rằng `connect()` thành công chứng minh một ứng dụng nghiệp vụ đã nhận request: nó mới chứng minh TCP connection đã được thiết lập.

## 8. Echo văn bản: tự định nghĩa framing bằng newline và UTF-8

TCP **chỉ truyền một dòng byte có thứ tự**, không cung cấp API “nhận đúng một message” cho mỗi `write`. Vì demo muốn echo các câu văn bản, ta định nghĩa giao thức ứng dụng:

~~~text
CLIENT GỬI, UTF-8:
xin chào\n
TCP Java 17\n
line=3\n
[FIN: shutdownOutput()]

SERVER TRẢ, UTF-8:
ECHO:xin chào\n
ECHO:TCP Java 17\n
ECHO:line=3\n
[EOF khi server đóng Socket]
~~~

Các chuỗi `\n` trên sơ đồ biểu diễn **ký tự xuống dòng**, không phải server bắt buộc nhận đúng một lần `read()` cho mỗi dòng. Java `BufferedReader.readLine()` nhận dữ liệu đến khi có line terminator hoặc EOF rồi bỏ delimiter; nó trả **`null`** khi đã đến hết input stream.

Kết hợp:

- `new InputStreamReader(socket.getInputStream(), UTF_8)` để decode byte thành ký tự.
- `new BufferedReader(...)` và `readLine()` để nhận từng dòng theo framing.
- `new OutputStreamWriter(socket.getOutputStream(), UTF_8)` để mã hóa văn bản thành UTF-8.
- `new BufferedWriter(...)`, `write(...)`, `newLine()` và `flush()` để gửi các dòng đã được buffer.

**`flush()` rất quan trọng** với buffered output: các byte có thể đang ở trong bộ đệm của `BufferedWriter`, chưa được chuyển tiếp sang socket. Nếu server chờ newline trong khi client chưa flush, hai phía có thể chờ nhau.

**Giới hạn của line protocol:** payload không nên chứa newline chưa được escape; encoding phải thống nhất; `readLine()` không tự giới hạn số ký tự của một dòng. Với dữ liệu người dùng không tin cậy, production cần giới hạn chiều dài từng frame/line, charset decoding và tổng bytes. Demo chỉ gửi ba dòng nhỏ định trước.

## 9. Chương trình Java 17+ số 1: echo ba dòng Unicode qua loopback

Tạo file **`TcpEchoLinesDemo.java`**. Chương trình mở `ServerSocket(0,16,127.0.0.1)` trước, chạy `accept()` trên worker, client connect vào `getLocalPort()`, gửi ba dòng UTF-8 rồi gọi `shutdownOutput()`. Server gửi lại `ECHO:...` cho từng dòng và kết thúc khi thấy EOF. Client đọc cho tới EOF, kiểm tra toàn bộ echo và in kết quả ổn định.

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class TcpEchoLinesDemo {
    private static int serveOne(ServerSocket listener) throws IOException {
        try (Socket peer = listener.accept()) {
            peer.setSoTimeout(5_000);
            BufferedReader input = new BufferedReader(new InputStreamReader(
                    peer.getInputStream(), StandardCharsets.UTF_8));
            BufferedWriter output = new BufferedWriter(new OutputStreamWriter(
                    peer.getOutputStream(), StandardCharsets.UTF_8));
            int count = 0;
            String line;
            while ((line = input.readLine()) != null) {
                output.write("ECHO:" + line);
                output.newLine();
                output.flush();
                count++;
            }
            return count;
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 16, InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(5_000);
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<Integer> serverCount =
                        executor.submit(() -> serveOne(listener));
                try (Socket client = new Socket()) {
                    client.connect(new InetSocketAddress(
                            "127.0.0.1", listener.getLocalPort()), 3_000);
                    client.setSoTimeout(5_000);

                    BufferedWriter output = new BufferedWriter(
                            new OutputStreamWriter(client.getOutputStream(),
                                    StandardCharsets.UTF_8));
                    BufferedReader input = new BufferedReader(
                            new InputStreamReader(client.getInputStream(),
                                    StandardCharsets.UTF_8));

                    List<String> messages = List.of(
                            "xin chào", "TCP Java 17", "line=3");
                    for (String message : messages) {
                        output.write(message);
                        output.newLine();
                    }
                    output.flush();
                    client.shutdownOutput(); // FIN: no more client bytes.

                    List<String> actual = new ArrayList<>();
                    String response;
                    while ((response = input.readLine()) != null) {
                        actual.add(response);
                    }
                    List<String> expected = messages.stream()
                            .map(message -> "ECHO:" + message).toList();
                    if (!actual.equals(expected)) {
                        throw new AssertionError(
                                "echo mismatch: " + actual);
                    }

                    System.out.println("bound to loopback: "
                            + listener.getInetAddress().isLoopbackAddress());
                    System.out.println("OS assigned port: "
                            + (listener.getLocalPort() > 0));
                    for (int i = 0; i < actual.size(); i++) {
                        System.out.println("echo " + (i + 1) + ": "
                                + actual.get(i));
                    }
                }
                System.out.println("server line count: "
                        + serverCount.get(5, TimeUnit.SECONDS));
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file:

~~~bash
javac TcpEchoLinesDemo.java
java TcpEchoLinesDemo
~~~

Kết quả đã kiểm thử:

~~~text
bound to loopback: true
OS assigned port: true
echo 1: ECHO:xin chào
echo 2: ECHO:TCP Java 17
echo 3: ECHO:line=3
server line count: 3
~~~

**Không in con số cổng cụ thể trong expected output**, vì OS có thể cấp cổng khác mỗi lần chạy. `OS assigned port: true` xác nhận cổng thực sau bind dương. Chương trình kiểm tra bằng `List.equals` rằng cả ba echo khớp **chính xác** thứ tự và nội dung mong đợi, không chỉ kiểm tra có ba dòng.

## 10. Mổ xẻ trình tự của chương trình echo văn bản

1. **Listener đã sẵn sàng:** `new ServerSocket(0,16,InetAddress.getByName("127.0.0.1"))` bind trước khi thread client kết nối. `getLocalPort()` được dùng trực tiếp, không đặt port cố định.
2. **Server worker:** `executor.submit(() -> serveOne(listener))` chạy `accept()` ở thread khác. `Future<Integer>` lưu số dòng server đã xử lý; không in trực tiếp từ thread server để tránh output race.
3. **Kết nối:** client gọi `connect(new InetSocketAddress("127.0.0.1", listener.getLocalPort()),3000)`. Phía server `accept()` trả `peer` tương ứng.
4. **Gửi:** client ghi ba dòng bằng `BufferedWriter`, mỗi dòng có `newLine()`, sau đó `flush()`. `flush` được gọi **trước `shutdownOutput()`** để không bỏ sót byte còn ở buffer của Java.
5. **Half-close:** `client.shutdownOutput()` cho server biết **sẽ không có thêm byte từ client**, nhưng **chiều server → client vẫn có thể truyền dữ liệu**. Đây là điểm quan trọng để không đóng luôn socket khi client còn cần echo.
6. **Phía server:** `while ((line = input.readLine()) != null)` đọc từng dòng; với mỗi dòng, viết `"ECHO:" + line`, xuống dòng và flush. Khi client half-close, `readLine` trả null sau khi tiêu thụ byte còn lại.
7. **Server đóng peer:** ra khỏi `try (Socket peer = listener.accept())` thì socket kết nối đóng. Client nhận đủ echo rồi thấy EOF khi `input.readLine()` trả null.
8. **Đối chiếu:** client so `actual` và `messages.stream().map(...).toList()`. Nếu echo sai, ném `AssertionError` và demo fail thay vì in thành công giả.
9. **Worker result:** `serverCount.get(5, TimeUnit.SECONDS)` lấy số dòng đã xử lý, dự kiến 3. Cuối cùng `executor.shutdownNow()` và `listener.close()` giải phóng tài nguyên.

Đầu ra được in ở thread main sau khi đã nhận đủ echo, nên **không phụ thuộc thread server chạy nhanh hay chậm**. Một máy có tốc độ khác có thể có port khác, nhưng các dòng kiểm thử vẫn đúng khi loopback hoạt động và không gặp timeout.

## 11. Vì sao cần shutdownOutput thay vì close ngay?

`Socket.shutdownOutput()` và `Socket.close()` rất khác nhau:

| Lệnh | Chiều client → server | Chiều server → client | Dùng khi nào? |
| --- | --- | --- | --- |
| `client.shutdownOutput()` | Báo kết thúc chiều gửi, peer có thể thấy EOF sau dữ liệu | **Vẫn còn mở** để client đọc echo | Client đã gửi xong nhưng cần chờ response |
| `client.close()` | Đóng socket và các stream | Không dùng tiếp để nhận echo | Trao đổi đã hoàn tất hoặc cleanup lỗi |
| `serverPeer.close()` | Đóng kết nối đã accept ở server | Client thường nhận EOF sau các byte còn gửi | Server đã xử lý xong |
| `client.shutdownInput()` | Ảnh hưởng **chiều nhận của client**, không phải tín hiệu kết thúc gửi | Client không nên tiếp tục đọc echo | **Không cần** trong giao thức bài này |

Sơ đồ tránh deadlock:

~~~text
Nếu client gửi "hello\n" rồi chờ server đóng connection:
  client: chờ EOF để biết đã hết echo
  server: chờ EOF để biết client đã gửi hết request
  => cả hai có thể chờ nhau.

Giải pháp của bài:
  client: flush -> shutdownOutput() -> đọc echo cho tới EOF
  server: đọc tới EOF -> đóng peer
  => cả hai có tín hiệu kết thúc rõ ràng.
~~~

Không hiểu `shutdownOutput()` là “đã ngắt TCP connection”. TCP có thể **half-close** một hướng trong khi hướng còn lại vẫn hoạt động. Nếu dùng `try-with-resources` đóng client ngay sau gửi mà chưa đọc, response có thể bị mất và bài test không chứng minh echo thành công.

`shutdownOutput` là lựa chọn phù hợp cho **giao thức gửi hết request rồi đọc response**. Với protocol request/response dài hạn nhiều lượt trên cùng connection, nên có **length prefix/delimiter** để biết từng message kết thúc, thay vì yêu cầu half-close sau mỗi request.

## 12. TCP không giữ ranh giới write: đừng đọc một lần rồi coi là một message

TCP đảm bảo thứ tự các byte được truyền thành công trong một kết nối, nhưng **không giữ ranh giới lệnh `write`** của ứng dụng. Ví dụ client gọi:

~~~java
output.write(new byte[] {1, 2});
output.write(new byte[] {3, 4, 5});
~~~

*Đoạn minh họa: `output` là một `OutputStream` thuộc socket đã kết nối.*

Server có thể nhận các byte đó qua `read(buffer)` thành nhóm `[1]`, `[2,3,4]`, `[5]` hoặc các nhóm khác, tùy OS và thời điểm dữ liệu đến. **Không có cam kết** hai lần `write` tạo hai lần `read` tương ứng.

Nếu `read(byte[])` trả `n`, chỉ các phần tử `buffer[0]` đến `buffer[n-1]` là dữ liệu mới đọc. Phần còn lại của buffer không thuộc kết quả lần này. Phải ghi lại **đúng `n` byte**:

~~~java
byte[] buffer = new byte[4096];
int n;
while ((n = input.read(buffer)) != -1) {
    output.write(buffer, 0, n);
}
output.flush();
~~~

*Đoạn minh họa có `input`/`output` là stream của socket. Việc chờ EOF phù hợp với giao thức của ví dụ, không phải mọi protocol mạng.*

- `n > 0`: xử lý đúng n bytes, không đọc phần cũ của buffer.
- `n == -1`: đối phương đã kết thúc luồng gửi theo hướng tương ứng và dữ liệu đã được tiêu thụ; không đồng nghĩa mỗi command nghiệp vụ đã thành công.
- Nếu socket bị reset/hỏng, `read` có thể ném `SocketException`/`IOException` thay vì trả `-1`.
- `read()` có thể chặn nếu chưa có dữ liệu/EOF; `setSoTimeout` giới hạn thời gian một read chờ.
- Với buffer không rỗng, một lệnh `read(byte[])` **không có nghĩa sẽ đầy buffer**; cần loop cho đến ranh giới framing hoặc EOF.

Đây là lý do server binary echo ở phần sau dùng `output.write(buffer,0,n)`, không dùng `output.write(buffer)`.

## 13. Chương trình Java 17+ số 2: echo bảy byte nhị phân

Tạo file **`TcpEchoBytesDemo.java`**. Chương trình minh họa **cách bind thứ hai**: `new ServerSocket()` rồi `listener.bind(new InetSocketAddress("127.0.0.1",0),16)`. Server đọc bằng buffer **3 byte**, echo đúng `n` byte mỗi lần. Client gửi mảng có cả byte NUL `0x00`, newline `0x0A` và `0xFF`, sau đó half-close chiều gửi và gom dữ liệu echo.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class TcpEchoBytesDemo {
    private static int serveOne(ServerSocket listener) throws Exception {
        try (Socket peer = listener.accept()) {
            peer.setSoTimeout(5_000);
            InputStream input = peer.getInputStream();
            OutputStream output = peer.getOutputStream();
            byte[] buffer = new byte[3];
            int total = 0;
            int n;
            while ((n = input.read(buffer)) != -1) {
                output.write(buffer, 0, n);
                total += n;
            }
            output.flush();
            return total;
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress("127.0.0.1", 0), 16);
            listener.setSoTimeout(5_000);
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<Integer> serverCount =
                        executor.submit(() -> serveOne(listener));
                byte[] payload = new byte[] {
                        0, 1, 2, 3, (byte) 0xff, 10, 0 };
                byte[] echoed;
                try (Socket client = new Socket()) {
                    client.connect(new InetSocketAddress(
                            "127.0.0.1", listener.getLocalPort()), 3_000);
                    client.setSoTimeout(5_000);
                    client.getOutputStream().write(payload);
                    client.getOutputStream().flush();
                    client.shutdownOutput();

                    ByteArrayOutputStream received = new ByteArrayOutputStream();
                    byte[] chunk = new byte[4];
                    int n;
                    while ((n = client.getInputStream().read(chunk)) != -1) {
                        received.write(chunk, 0, n);
                    }
                    echoed = received.toByteArray();
                }
                System.out.println("OS assigned port: "
                        + (listener.getLocalPort() > 0));
                System.out.println("echoed bytes match: "
                        + Arrays.equals(payload, echoed));
                System.out.println("echoed signed bytes: "
                        + Arrays.toString(echoed));
                System.out.println("server byte count: "
                        + serverCount.get(5, TimeUnit.SECONDS));
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac TcpEchoBytesDemo.java
java TcpEchoBytesDemo
~~~

Stdout đã kiểm thử:

~~~text
OS assigned port: true
echoed bytes match: true
echoed signed bytes: [0, 1, 2, 3, -1, 10, 0]
server byte count: 7
~~~

**Tại sao `0xFF` in ra `-1`?** Kiểu `byte` của Java có dấu (từ `-128` đến `127`), vì thế `(byte) 0xff` khi `Arrays.toString(byte[])` sẽ hiển thị **-1**. Đây **không phải** `InputStream.read() == -1`. Ở cấp API `InputStream.read(byte[])`, **giá trị trả về của chính hàm** `-1` mới biểu thị EOF, còn byte `0xFF` trong **mảng dữ liệu** vẫn hợp lệ. `Arrays.equals(payload, echoed) == true` kiểm chứng mọi byte được echo chính xác.

Mặc dù server dùng buffer 3 byte, không được khẳng định mỗi `read` thực tế **luôn nhận đúng ba byte**. Buffer nhỏ giới hạn **số byte tối đa trong một lần read**; số byte cụ thể tùy thời điểm TCP stream đưa dữ liệu tới. Tổng `server byte count: 7` mới là tín hiệu ổn định trong bài test.

## 14. Hai cách bind port 0 — so sánh rõ ràng

| Cách | Trạng thái khi tạo | Thao tác bind | Điểm chung |
| --- | --- | --- | --- |
| `new ServerSocket(0,16,InetAddress.getByName("127.0.0.1"))` | **Đã bind** khi constructor hoàn tất | Trong constructor | OS chọn port, IPv4 loopback |
| `new ServerSocket()` | **Chưa bind** | `bind(new InetSocketAddress("127.0.0.1",0),16)` | OS chọn port, IPv4 loopback |

**Cả hai** đều cần `accept()` để lấy socket của client. **Cả hai** dùng `getLocalPort()` sau bind. **Không** tạo `Socket` phía client kết nối vào port 0. **Không** gửi dữ liệu trực tiếp qua `ServerSocket`.

Nếu server cần chọn cấu hình IP/backlog ở thời điểm muộn, cách thứ hai cho phép tạo object trước và bind sau. Trong bài test đơn giản, cách đầu gọn hơn. Nếu bind địa chỉ không khả dụng hoặc port đã bị chiếm (với port cố định), có thể gặp `BindException`/`IOException`; với port 0, OS giảm rủi ro collision nhưng không có nghĩa mọi vấn đề networking đều biến mất.

## 15. Framing cho TCP thực tế: các phương án thường dùng

| Chiến lược | Ranh giới message | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| **Newline-delimited text** | `\n` hoặc newline hợp lệ | Rất dễ debug, phù hợp echo text | Payload có newline cần escaping; giới hạn chiều dài |
| **Length-prefix** | Ví dụ 4-byte length + N bytes payload | Hỗ trợ nhị phân và nhiều messages liên tiếp | Phải kiểm tra length, byte order, tối đa N |
| **Fixed-size frame** | Mỗi record N bytes | Đơn giản nếu schema cố định | Khó mở rộng; phải đọc đủ N bytes |
| **Delimiter bất kỳ** | Ký tự/byte phân cách đã quy định | Dễ đọc trong protocol đơn giản | Cần escape/encode delimiter trong payload |
| **EOF-delimited single message** | Một phía `shutdownOutput()`/close send | Dễ cho **một payload duy nhất** | Không hỗ trợ nhiều request/response trên kết nối liên tục mà không thêm framing |
| **Protocol chuẩn** | HTTP, WebSocket, v.v. | Có framing/semantics được định nghĩa | Cần tuân thủ protocol, không tự trộn raw TCP |

Ví dụ khái niệm length-prefix:

~~~text
Message 1:
  00 00 00 05 | 48 65 6C 6C 6F
      len=5    |     "Hello"

Message 2:
  00 00 00 03 | 01 02 03
      len=3    |   3 binary bytes
~~~

Với Java, `DataOutputStream.writeInt(length)` sử dụng 4 byte big-endian; `DataInputStream.readInt()` có thể đọc phần header length theo giao thức tương ứng. Sau khi xác thực `0 <= length <= MAX_FRAME_SIZE`, dùng `readFully(byte[])` hoặc vòng đọc đủ byte; nếu EOF đến trước số byte mong đợi, xử lý `EOFException` như **message bị cắt cụt**, không coi là một message hoàn chỉnh.

**Bảo mật framing:** Không bao giờ cấp phát `new byte[length]` khi `length` do peer kiểm soát mà chưa kiểm tra giới hạn, không tin mọi client gửi đủ byte. Với UTF-8, byte length khác số Java chars/codepoints; cần đặt giới hạn theo **bytes** phù hợp với tài nguyên server.

## 16. Timeout và ngoại lệ: connect, accept, read không phải một thứ

| Hoạt động | Cách giới hạn trong demo | Khi timeout/lỗi |
| --- | --- | --- |
| Server chờ một client | `ServerSocket.setSoTimeout(5_000)` trước `accept()` | `SocketTimeoutException` nếu chờ accept quá hạn |
| Client thiết lập TCP connection | `Socket.connect(addr,3_000)` | `SocketTimeoutException` hoặc `ConnectException`/I/O error tùy trường hợp |
| Đọc dữ liệu trên một `Socket` | `Socket.setSoTimeout(5_000)` | `SocketTimeoutException` khi **một read** chờ lâu |
| Chờ server worker hoàn thành | `Future.get(5, TimeUnit.SECONDS)` | `TimeoutException` ở thread chờ, không tự đóng socket |
| Ghi dữ liệu | `OutputStream.write` | Có thể chặn/IOException; `SO_TIMEOUT` không phải hạn ghi tổng |
| Đóng/half-close | `shutdownOutput`, `close` | Có thể ném `IOException` khi trạng thái không hợp lệ/lỗi I/O |

**Không nhầm EOF với timeout:** `BufferedReader.readLine()==null` hoặc `InputStream.read(...) == -1` trong hoàn cảnh hợp lệ biểu thị peer đã kết thúc **chiều gửi**. `SocketTimeoutException` nghĩa là chờ quá lâu khi đọc/accept mà chưa có đủ sự kiện để tiếp tục. `Connection reset` thường là lỗi TCP bất thường, không phải dấu chấm hết của một message được gửi chuẩn.

Không coi `EOF` sau khi đã nhận **một phần** frame length-prefix là thành công: đó là dữ liệu **truncated**. Ví dụ echo này biết trước ba dòng và bảy byte nên kiểm tra toàn bộ nội dung; các ứng dụng thật cần độ dài, checksum hoặc protocol response để biết đã nhận đủ.

`setSoTimeout` không phải deadline tổng cho cả cuộc gọi dài và không ngăn một peer chậm gửi từng byte vừa đủ trước timeout. Production cần thêm deadline tổng, giới hạn số bytes/lines, quota và chính sách hủy/đóng socket.

## 17. Tài nguyên và trật tự đóng kết nối

Cả hai chương trình dùng `try (ServerSocket listener = ...)` cho listening socket và `try (Socket peer = listener.accept())` / `try (Socket client = new Socket())` cho các kết nối đã chấp nhận hoặc chủ động tạo. Đóng `Socket` sẽ đóng các input/output streams liên quan. Đây là cách tránh “port vẫn bận vì process chưa đóng socket”.

Thứ tự trong bài test:

~~~text
1. Bind ServerSocket(127.0.0.1, 0)
2. Khởi chạy worker chờ accept()
3. Client connect vào cổng thực
4. Client gửi và flush dữ liệu
5. Client shutdownOutput()
6. Server đọc tới EOF, echo, đóng accepted Socket
7. Client đọc echo tới EOF và đối chiếu
8. Client close, server worker hoàn tất
9. Shutdown executor rồi đóng ServerSocket
~~~

`serverCount.get(...)` được gọi khi client đã đọc hết response và đóng, nên server task đã có cơ hội hoàn tất. `executor.shutdownNow()` trong `finally` giúp dọn worker; nếu worker bị kẹt trên I/O thì interrupt có thể **không đủ** để giải phóng mọi lời gọi socket cổ điển, vì thế cần kết hợp timeouts và đóng socket/listener. Demo đặt timeout giới hạn cho accept/read để tránh treo vô hạn trong điều kiện thông thường.

**ServerSocket.close() khác Socket.close():** đóng listener dừng chấp nhận kết nối mới; các accepted sockets có vòng đời riêng. Trong server nhiều client, phải quản lý và đóng các accepted sockets riêng, chứ không dựa vào chỉ đóng listening socket là mọi client đã được cleanup.

## 18. Nếu muốn echo nhiều client đồng thời

Hai demo cố ý nhận **một** connection để test đơn giản. Muốn chạy một TCP echo service dài hạn, mô hình thường là:

~~~text
ServerSocket listener đã bind
        |
while (running):
    Socket peer = listener.accept()
        |
        +--> bounded executor xử lý peer và đóng peer sau phiên
        |
shutdown:
    dừng accept -> đóng listener -> đợi worker có deadline -> cleanup
~~~

Thiết kế production phải đặt giới hạn số connections đang active, số threads, kích thước queue, số bytes per client, thời gian chờ và cơ chế auth/TLS theo nhu cầu. Không tạo một platform thread vô hạn cho mỗi client nếu kẻ tấn công có thể mở rất nhiều connections.

Một số thay đổi hợp lý khi mở rộng:

- Giữ `ServerSocket` chung và cho mỗi accepted `Socket` một handler độc lập; không trộn streams của hai clients.
- Dùng `ExecutorService` có giới hạn, chính sách reject/quota và graceful shutdown.
- Tránh chia sẻ `BufferedReader`, `BufferedWriter` hay `Socket` của cùng một client giữa nhiều writers không đồng bộ.
- Với nhiều messages trên connection lâu dài, dùng framing explicit chứ không trông chờ EOF sau mỗi request.
- Nếu cần backpressure/scale lớn, cân nhắc Java NIO `SocketChannel`/`Selector`, nhưng đây là hướng mở rộng, **không cần** để hoàn tất bài TCP echo cơ bản.

## 19. Tại sao demo không “mở mạng ra ngoài”?

Demo bind `127.0.0.1` nên các connections chỉ đến từ namespace mạng local tương ứng, không expose trực tiếp trên LAN theo cấu hình thông thường. Tuy nhiên **loopback không thay thế xác thực** khi có tiến trình không tin cậy cùng máy hoặc khi môi trường có port forwarding/proxy/container networking.

`Socket` và `ServerSocket` trong ví dụ truyền **TCP plaintext**, **không có TLS**. Không gửi thông tin nhạy cảm hay credential thật. Nếu cần mã hóa/xác thực trong hệ thống thực, có thể dùng `SSLSocket`/`SSLServerSocket` hoặc giao thức an toàn phù hợp; phải xác minh certificates và hostname, không dùng “trust-all”.

Bên cạnh bind loopback, nên tránh ghi nội dung cá nhân nhạy cảm vào log của demo và không giả định firewall, container hoặc runner CI cho phép mọi loopback connection. Nếu môi trường hạn chế socket binding, bài test có thể bị từ chối dù source code đúng.

## 20. Những lỗi phổ biến nhất

| Hiểu nhầm hoặc code sai | Hậu quả | Cách sửa |
| --- | --- | --- |
| Server bind `port=0` rồi client connect `port=0` | Client dùng sai endpoint | Lấy `ServerSocket.getLocalPort()` |
| Hard-code `8080` dù OS vừa cấp cổng khác | `Connection refused` | Dùng đúng port đã bind |
| Mở socket lấy port rồi đóng trước khi server bind | Race bị process khác chiếm port | Giữ chính listener đã bind cổng 0 |
| Bind IPv6 loopback nhưng connect IPv4 loopback | Họ địa chỉ không khớp | Dùng `127.0.0.1` ở cả hai phía |
| Bind `0.0.0.0` khi chỉ cần local | Có thể mở ra interface mạng ngoài | Bind loopback tường minh |
| Gọi `accept()` trước `connect()` trên cùng thread | Thread đứng chờ mãi | Dùng worker khác cho server |
| Không `flush()` sau `BufferedWriter.write` | Server chờ newline/data trong buffer | Flush đúng lúc |
| Gửi text nhưng không định nghĩa delimiter/length | `readLine()` hoặc parser chờ mãi | Có framing rõ |
| `readLine() == ""` nghĩa EOF | Nhầm dòng trống hợp lệ | EOF là `null` |
| `read(buffer)` một lần rồi tưởng nhận đủ message | Dữ liệu có thể tới theo nhiều chunks | Vòng lặp tới frame boundary |
| `output.write(buffer)` bỏ qua `n` thực đọc | Gửi byte cũ/thừa trong buffer | `write(buffer,0,n)` |
| So một byte `0xFF` với return `-1` của `read` | Nhầm dữ liệu với EOF | Phân biệt signed byte với số byte đọc |
| Client `close()` trước khi nhận echo | Đánh mất chiều đọc response | `shutdownOutput` rồi đọc đến EOF |
| Cả client/server đều đợi EOF nhưng không half-close | Có thể deadlock | Thiết kế tín hiệu kết thúc |
| Tin rằng `setSoTimeout` giới hạn toàn bộ phiên | Peer chậm có thể kéo dài qua nhiều reads | Có total deadline và size limit |
| Không dùng try-with-resources | Rò rỉ sockets/port/thread | Đóng cả listener, peers, executor |
| Dùng `readAllBytes()` cho stream không giới hạn | Có thể hết RAM hoặc chờ EOF vô hạn | Bounded reading và framing |
| Cho rằng TCP có sẵn “gửi đúng một lần” nghiệp vụ | TCP chỉ chuyển luồng byte | ACK/idempotency ở tầng ứng dụng |
| Truyền bằng `getBytes()` charset mặc định | Khác máy có thể lỗi tiếng Việt | `StandardCharsets.UTF_8` |
| Cho rằng backlog là số client xử lý đồng thời | Sai ý nghĩa hàng đợi accept | Tách backlog và worker concurrency |

## 21. Kiểm thử chương trình theo từng lớp

Một bài test tốt nên xác minh từng lớp, không chỉ “không ném exception”:

1. **Bind đúng:** `listener.getInetAddress().isLoopbackAddress()==true` và `getLocalPort()>0`. Không cần biết con số port.
2. **Kết nối đúng:** client gọi `connect` đến đúng IPv4/port. Nếu sai port, thường gặp `ConnectException`.
3. **Framing:** demo line nhận đúng **ba** lines và mỗi echo bắt đầu `ECHO:`, có dấu tiếng Việt UTF-8 chính xác.
4. **EOF/half-close:** client `shutdownOutput()`, server thoát `readLine` khi EOF, client nhận được echo rồi thấy EOF do server đóng.
5. **Byte integrity:** demo binary dùng `Arrays.equals` để so đủ 7 byte, bao gồm NUL và `0xFF`.
6. **Read counts:** server chỉ ghi `n` byte mỗi lần nhận, tổng đếm đúng 7; không giả định từng `read` nhận đúng kích thước buffer.
7. **Cleanup:** server worker hoàn tất, socket/listener đóng. Chạy lại chương trình nhiều lần mà không có xung đột port cố định.
8. **Timeout:** một client/peer không gửi dữ liệu cần có behavior timeout rõ; không để test đứng vô hạn.
9. **Negative tests:** thử kết nối cổng sai, server không phản hồi, lỗi framing/truncated frame rồi phân loại exception đúng.

Vì hai chương trình in các giá trị boolean thay vì số port ngẫu nhiên, stdout có thể kiểm tra chính xác. Nếu loopback được phép và không bị timeout bởi máy quá tải, thứ tự và số dòng đầu ra không phụ thuộc lập lịch worker.

## 22. Câu hỏi kiểm tra kiến thức

**Câu 1.** `new ServerSocket(0,16,InetAddress.getByName("127.0.0.1"))` có tạo server lắng nghe ở port 0 không?

*Đáp án:* Không theo cách client sử dụng. Port 0 **yêu cầu OS cấp một cổng thực**, và port đó được đọc bằng `getLocalPort()` sau bind.

**Câu 2.** `ServerSocket.accept()` trả gì, và có dùng `ServerSocket` để đọc dữ liệu client không?

*Đáp án:* `accept()` trả **`Socket` mới** đại diện một kết nối được nhận. Đọc/ghi bằng input/output streams của Socket đó, không bằng ServerSocket.

**Câu 3.** Vì sao phải chạy `accept()` và `connect()` trên các threads khác nhau trong demo?

*Đáp án:* `accept()` chặn chờ client; nếu gọi trước `connect()` trên cùng thread thì connect không bao giờ được khởi phát.

**Câu 4.** Client gửi ba lần `write` nhưng server `read` hai lần có sai TCP không?

*Đáp án:* Không. TCP là luồng byte; ranh giới `write` không đồng nhất với ranh giới `read`. Phải tự framing và xử lý đúng n bytes.

**Câu 5.** `BufferedReader.readLine()` trả chuỗi rỗng có phải EOF không?

*Đáp án:* Không. Dòng rỗng là `""`. EOF là `null`.

**Câu 6.** Tại sao client dùng `shutdownOutput()` thay vì `close()` ngay sau gửi?

*Đáp án:* `shutdownOutput()` thông báo không còn byte gửi nhưng vẫn cho phép nhận echo; `close()` đóng luôn cả socket và không thể tiếp tục đọc.

**Câu 7.** `Arrays.toString(new byte[]{(byte)0xff})` in `[-1]`. Đó có phải TCP EOF không?

*Đáp án:* Không. Kiểu `byte` của Java có dấu. EOF chỉ là **giá trị int trả về của lệnh `InputStream.read`**, không phải byte dữ liệu có giá trị `0xFF`.

**Câu 8.** `Socket.setSoTimeout(5000)` có bảo đảm cả phiên TCP kết thúc trong 5 giây không?

*Đáp án:* Không. Nó giới hạn thời gian chờ của **mỗi read có áp dụng**; cần deadline phiên và giới hạn dữ liệu riêng.

**Câu 9.** Vì sao `127.0.0.1` khác `0.0.0.0` trong khi bind?

*Đáp án:* `127.0.0.1` là loopback chỉ phục vụ local; `0.0.0.0` lắng nghe các IPv4 interfaces và có thể phơi bày service lên mạng ngoài.

## 23. Bài tập thực hành

1. Chạy `TcpEchoLinesDemo` trên Java 17+, thay ba dòng test bằng nội dung tiếng Việt mới, xác minh `List.equals` vẫn PASS và echo giữ đúng Unicode.
2. Thử in giá trị thật của `listener.getLocalPort()` trong lần chạy riêng, chạy lại vài lần để quan sát OS chọn cổng; **không hard-code** số ấy vào test output chính.
3. Chuyển demo 1 sang `new ServerSocket()` rồi `bind(new InetSocketAddress("127.0.0.1",0),16)`; giải thích hai giai đoạn create và bind.
4. Bỏ `output.flush()` (trong một bản copy để test) rồi giải thích vì sao server có thể chờ buffered bytes và xuất hiện timeout; khôi phục flush.
5. Bỏ `client.shutdownOutput()` rồi dự đoán client/server sẽ chờ gì; quan sát socket timeout trong bản test có hạn thời gian, khôi phục half-close.
6. Trong demo line, gửi dòng rỗng `""`; xác minh nó được echo thành `ECHO:` và **không** nhầm EOF.
7. Trong demo binary, đổi buffer server từ 3 thành 1 và 8, xác nhận `Arrays.equals` luôn đúng, dù số lần `read` thay đổi.
8. Thêm payload có `0x00`, `0xFF` và byte UTF-8 không hợp lệ như dữ liệu raw; kiểm tra echo byte-for-byte, không decode thành text.
9. Cố ý sửa server thành `output.write(buffer)` thay vì `write(buffer,0,n)`, xem dữ liệu thừa xuất hiện ở chunk cuối; khôi phục phiên bản đúng.
10. Thiết kế length-prefix frame 4-byte big-endian + payload (giới hạn tối đa 4096 bytes), dùng `DataInputStream.readFully` để đọc đủ từng message, và trả lỗi khi EOF trước độ dài đã khai báo.
11. Mở rộng server thành vòng `accept` với bounded executor và giới hạn tối đa client, đảm bảo accepted socket được đóng trong mỗi handler.
12. Thử connect đến một port chưa có listener và phân loại `ConnectException`, không nhầm với `SocketTimeoutException` hoặc EOF.
13. Chạy trên môi trường container/CI, chỉ rõ loopback namespace và điều kiện cho client/test nằm cùng namespace.
14. Viết cleanup checklist cho graceful shutdown: stop accepting, close listener, drain/close accepted sockets và shutdown executor theo deadline.
15. Thảo luận nếu echo server phục vụ dữ liệu nhạy cảm thật: cần TLS, giới hạn message length, auth, không ghi dữ liệu nhạy cảm vào log và bảo vệ khỏi denial-of-service.

## Tài liệu API chính thức

- [`ServerSocket` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): constructors, `bind`, port 0, `getLocalPort`, `accept`, `setSoTimeout`, `close`.
- [`Socket` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): `connect`, `setSoTimeout`, input/output streams, `shutdownOutput`, half-close, `close`.
- [`InputStream` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): `read(byte[])`, số byte thực đọc và `-1` tại EOF.
- [`BufferedReader` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html): `readLine()`, `null` khi hết dòng.
- [`BufferedWriter` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html): `newLine`, `flush` và buffering.
- [`DataInputStream` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readInt`, `readFully` cho framing có độ dài.
- [`StandardCharsets` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): bộ mã `UTF_8` để trao đổi văn bản nhất quán.
