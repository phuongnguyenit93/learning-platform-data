# Phân biệt `Socket.isConnected()`, `Socket.isClosed()` với khả năng trao đổi dữ liệu hiện tại

Khi làm việc với TCP bằng `java.net.Socket`, một câu kiểm tra tưởng như hợp lý là:

~~~java
// Fragment minh họa, không phải cách xác nhận kết nối còn hoạt động.
if (socket.isConnected() && !socket.isClosed()) {
    socket.getOutputStream().write(requestBytes);
}
~~~

Điều kiện trên **không chứng minh đầu bên kia còn hoạt động hoặc sẽ nhận được dữ liệu**. `isConnected()` ghi nhận socket đã kết nối thành công trong quá khứ; `isClosed()` phản ánh socket phía Java cục bộ đã được đóng hay chưa. Chúng không phải thao tác kiểm tra trạng thái sống của kết nối TCP theo thời gian thực.

Bài học giải thích chính xác ý nghĩa hai phương thức, trạng thái sau khi phía bên kia đóng kết nối, EOF, lỗi I/O, timeout, TCP half-close và cách kiểm tra khả năng trao đổi dữ liệu bằng thao tác I/O cùng giao thức ứng dụng.

## 1. Hai cờ này thực sự trả lời câu hỏi nào?

Theo tài liệu Java SE 17 của `java.net.Socket`:

- **`isConnected()`:** trả `true` nếu socket **đã từng kết nối thành công** tới máy chủ. Việc gọi `close()` không xóa trạng thái kết nối đã đạt được. Vì thế, một socket đã đóng vẫn có thể có `isConnected() == true`.
- **`isClosed()`:** trả `true` nếu **đối tượng socket cục bộ đã được đóng** (ví dụ bằng `close()`, try-with-resources hoặc đóng stream gắn với socket). Đây không phải thông báo tức thời từ thiết bị ở phía bên kia.

Bảng các trạng thái thường gặp:

| Tình huống | `isConnected()` | `isClosed()` | Có thể kết luận gì? |
| --- | --- | --- | --- |
| Mới gọi `new Socket()`, chưa kết nối | `false` | `false` | Đối tượng được tạo nhưng chưa kết nối; chưa thể gửi/nhận qua TCP |
| `connect(...)` thành công và chưa đóng | `true` | `false` | Đã từng kết nối và chưa gọi đóng cục bộ; **chưa chắc peer còn sống** |
| Peer gửi TCP FIN (đóng chiều gửi), phía mình chưa `close()` | Thường là `true` | `false` | Có thể nhận EOF khi đọc hết dữ liệu đệm; cờ không tự trở thành “disconnected” |
| Mạng đứt hoặc peer mất nguồn, lỗi chưa được I/O phát hiện | `true` | `false` có thể vẫn giữ nguyên | Không được suy ra đường truyền đang tốt |
| Mình gọi `shutdownOutput()` (half-close chiều gửi) | `true` | `false` | Không gửi thêm được theo chiều này, nhưng vẫn có thể đọc dữ liệu |
| Socket đã từng kết nối, sau đó mình gọi `close()` | `true` | `true` | Đối tượng đã đóng và không được tái sử dụng |
| Socket chưa kết nối, sau đó mình gọi `close()` | `false` | `true` | Đối tượng chưa kết nối và đã đóng |

Chú ý: bảng mô tả **`Socket` kiểu blocking thông thường**. Không tự áp quy tắc này lên `SocketChannel.isConnected()` của Java NIO; theo Javadoc, `SocketChannel.isConnected()` còn gắn với điều kiện channel đang mở. Tương tự, `ServerSocket.isClosed()` chỉ nói về socket lắng nghe, không nói rằng mọi client đã chấp nhận đều đã đóng.

### Một suy luận rất dễ sai

~~~text
isConnected() == true
        |
        +--> ĐÚNG: socket này đã từng kết nối thành công
        |
        +--> SAI: peer chắc chắn đang chạy
        +--> SAI: gửi byte tiếp theo chắc chắn thành công
        +--> SAI: peer/application chắc chắn nhận và xử lý dữ liệu

isClosed() == false
        |
        +--> ĐÚNG: socket cục bộ chưa được đánh dấu đóng
        |
        +--> SAI: kết nối TCP còn thông suốt
        +--> SAI: phía bên kia chưa gửi FIN hoặc RST
~~~

Trường hợp `isConnected() == true && isClosed() == true` **không mâu thuẫn**: một cờ ghi lịch sử kết nối, một cờ ghi trạng thái đóng của đối tượng cục bộ.

## 2. Một kết nối TCP có thể hỏng sau khi kết nối thành công

Lời gọi `socket.connect(remote, timeout)` có thể thiết lập kết nối thành công ở thời điểm **t₀**. Nhưng sau đó máy chủ dừng, cáp mạng bị rút, route thay đổi, NAT hết hạn, firewall loại bỏ luồng hoặc peer gửi FIN/RST.

Không có lời gọi `Socket.isConnected()` nào bắt buộc mạng phải xác minh lại peer trước khi trả kết quả. `isClosed()` cũng không liên tục thực hiện kiểm tra từ xa. Điều kiện hai cờ được kiểm tra tại **t₁** còn có thể trở nên lỗi thời trước thao tác I/O tại **t₂**.

~~~text
t₀: TCP connect thành công
    isConnected=true, isClosed=false
           |
t₁: peer mất mạng / peer đóng chiều gửi / route hỏng
           |
    ứng dụng chưa làm I/O để biết
    isConnected=true, isClosed=false vẫn có thể đúng
           |
t₂: read() / write() / giao thức request-response
    mới có cơ hội nhận byte, EOF, timeout hoặc IOException
~~~

Kể cả một lần ghi thành công **cũng không phải bằng chứng ứng dụng ở đầu xa đã xử lý yêu cầu**. TCP và hệ điều hành có buffer; ghi có thể hoàn tất ở phía cục bộ trước khi peer nhận hoặc trước khi chương trình peer xử lý. Với yêu cầu cần bảo đảm ở tầng nghiệp vụ, cần xác nhận phản hồi hoặc ACK của **giao thức ứng dụng**.

## 3. Đọc dữ liệu: byte, EOF, timeout và lỗi không giống nhau

Với `InputStream` của socket:

| Kết quả | Ý nghĩa chủ yếu | Cách xử lý |
| --- | --- | --- |
| `read()` trả số từ `0` đến `255` | Đọc được một byte | Tiếp tục gom và giải mã theo framing của giao thức |
| `read()` trả `-1` | Đã tới **end-of-stream** | Đối với TCP, thường do peer đóng chiều gửi một cách có trật tự (FIN), **hoặc** input phía cục bộ đã bị `shutdownInput()` |
| `read(byte[])` trả số dương | Đã đọc được bấy nhiêu byte | Không giả định một lần đọc bằng một thông điệp ứng dụng |
| `SocketTimeoutException` | Lần đọc blocking quá hạn `SO_TIMEOUT` | Coi là thao tác hết thời gian; quyết định retry/close theo giao thức và deadline |
| `IOException` khác, ví dụ `SocketException` | Lỗi I/O: reset, đóng socket cục bộ, sự cố mạng... | Ghi nhận nguyên nhân, giải phóng socket lỗi và thực hiện chính sách phục hồi |

**EOF không đồng nghĩa “`isClosed()` sẽ thành `true`”.** Khi peer chỉ gửi FIN ở chiều truyền về mình, `read()` có thể trả `-1` sau khi đọc hết những byte đã nhận nhưng đối tượng `Socket` cục bộ vẫn chưa được đóng. TCP cho phép đóng một chiều; phía còn lại vẫn có thể có ý nghĩa theo giao thức.

**Không nhận được byte ngay bây giờ không đồng nghĩa EOF.** Nếu chưa có byte và peer chưa gửi FIN, `read()` blocking có thể tiếp tục chờ. `InputStream.available() == 0` chỉ nói rằng ở thời điểm kiểm tra không có byte bảo đảm đọc ngay mà không chặn; nó không chứng minh peer đã ngắt, cũng không chứng minh sẽ không có dữ liệu về sau.

**Không đồng nhất reset với FIN:** một số lỗi kết nối bất thường có thể dẫn đến `IOException`/`SocketException` thay vì EOF sạch. Java không hứa rằng mọi ngắt kết nối đều được quan sát như một `-1` ngay lập tức.

## 4. `close()` và `shutdownInput()/shutdownOutput()`: đóng toàn bộ hay một chiều?

TCP là luồng byte hai chiều. Hai hướng nhận và gửi có thể được kết thúc riêng:

- **`socket.shutdownOutput()`:** ngừng gửi byte thêm từ phía cục bộ. Với TCP, dữ liệu đã ghi trước đó được gửi tiếp rồi theo sau bằng chuỗi đóng chiều gửi thông thường (FIN). Các lệnh ghi tiếp sẽ ném `IOException`. Phía mình có thể **tiếp tục đọc** phản hồi từ peer.
- **`socket.shutdownInput()`:** đặt input của socket cục bộ vào trạng thái EOF; những lần `read()` tiếp theo trả `-1`. Đây là lựa chọn **do mình thực hiện**, nên không thể dùng riêng giá trị `-1` để suy ra chắc chắn rằng peer gửi FIN.
- **`socket.close()`:** đóng socket cục bộ và các stream của nó. Sau đó `isClosed() == true`; không tái sử dụng cùng đối tượng để kết nối lại. Nếu trước đó đã kết nối thành công, `isConnected()` vẫn trả `true`.

Cờ liên quan `isInputShutdown()` và `isOutputShutdown()` mô tả **trạng thái shutdown chiều đọc/ghi của socket cục bộ**. Việc phía bên kia gửi FIN không đồng nghĩa `isInputShutdown()` tự động thành `true`.

Ví dụ giao thức có thể yêu cầu: client gửi hết request → client `shutdownOutput()` → server đọc tới EOF để biết request đã kết thúc → server trả response → client tiếp tục đọc response. Đó là **half-close hợp lệ**, không phải ngay lập tức “mất kết nối” theo cả hai chiều.

~~~text
CLIENT                                      SERVER
write(request bytes) ---------------------> read(request bytes)
shutdownOutput() ---- TCP FIN -----------> read() == -1
     |
     |  client không gửi thêm
     |  nhưng input vẫn đọc được
     |
read(response bytes) <--------------------- write(response bytes)
read() == -1       <------- FIN ---------- shutdownOutput()/close()
close()
~~~

Không phải mọi giao thức đều dùng EOF để phân định request. HTTP/1.1 có framing thông qua header/length/chunked encoding; ứng dụng không được tự suy ra rằng luôn cần `shutdownOutput()` sau mỗi HTTP request.

## 5. Chương trình Java 17+ quan sát đúng các trạng thái

Ví dụ sau sử dụng `ServerSocket` ở loopback, tự chọn cổng đang trống (cổng `0`), không cần Internet hoặc DNS bên ngoài. Peer viết hai byte `OK` rồi gọi `shutdownOutput()`. Client đọc hết và thấy EOF, trong khi các cờ kết nối cục bộ vẫn giữ nguyên.

Lưu dưới đúng tên tệp **`SocketStateDemo.java`**:

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class SocketStateDemo {
    private static void state(String label, Socket socket) {
        System.out.printf(
                "%s: isConnected=%s isClosed=%s%n",
                label, socket.isConnected(), socket.isClosed());
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket listener = new ServerSocket(0, 1, loopback);
             Socket client = new Socket()) {
            state("new", client);

            client.connect(
                    new InetSocketAddress(
                            loopback, listener.getLocalPort()),
                    3_000);
            client.setSoTimeout(3_000);
            state("connected", client);

            try (Socket peer = listener.accept()) {
                peer.getOutputStream().write(
                        "OK".getBytes(StandardCharsets.UTF_8));
                peer.shutdownOutput();

                byte[] bytes =
                        client.getInputStream().readNBytes(2);
                System.out.println(
                        "received=" + new String(
                                bytes, StandardCharsets.UTF_8));

                System.out.println(
                        "readAfterPeerFIN="
                                + client.getInputStream().read());

                state("after-peer-FIN", client);
                System.out.println(
                        "peerFIN-inputShutdown="
                                + client.isInputShutdown());
                System.out.println(
                        "peerFIN-outputShutdown="
                                + client.isOutputShutdown());

                client.shutdownOutput();
                System.out.println(
                        "after-shutdownOutput="
                                + client.isOutputShutdown());
                state("after-local-shutdownOutput", client);
            }

            client.close();
            state("after-local-close", client);
        }
    }
}
~~~

Lệnh biên dịch/chạy trong thư mục chứa tệp:

~~~bash
javac SocketStateDemo.java
java SocketStateDemo
~~~

**Đầu ra mong đợi** với JDK 17+ và môi trường cho phép kết nối TCP loopback:

~~~text
new: isConnected=false isClosed=false
connected: isConnected=true isClosed=false
received=OK
readAfterPeerFIN=-1
after-peer-FIN: isConnected=true isClosed=false
peerFIN-inputShutdown=false
peerFIN-outputShutdown=false
after-shutdownOutput=true
after-local-shutdownOutput: isConnected=true isClosed=false
after-local-close: isConnected=true isClosed=true
~~~

Giải thích từng bước:

1. `new Socket()` tạo đối tượng chưa kết nối, chưa đóng. Cả hai cờ bằng `false`.
2. `client.connect(...)` thành công; `isConnected=true`. `setSoTimeout(3000)` giới hạn thời gian chờ mỗi lần đọc blocking, tránh bài thử chờ mãi nếu thiếu dữ liệu.
3. Server chấp nhận TCP, viết `OK` và gọi `shutdownOutput()`. Hai byte vẫn đến client; tiếp theo `client.read()` trả `-1` khi gặp FIN.
4. Sau EOF, client vẫn có `isConnected=true` và `isClosed=false`; hai cờ `isInputShutdown`/`isOutputShutdown` cũng vẫn `false` vì **client chưa tự shutdown hướng nào**.
5. Client gọi `shutdownOutput()` thì `isOutputShutdown=true`, nhưng `isClosed=false` vì vẫn chưa đóng toàn bộ socket.
6. Client gọi `close()`; `isClosed=true`. `isConnected` vẫn `true` vì lịch sử kết nối không bị xóa.

Lệnh `close()` xuất hiện tường minh để hiển thị cờ sau đóng; khi thoát khối `try-with-resources`, Java cũng đóng tài nguyên tự động. Việc gọi `close()` lại trên socket đã đóng không biến nó thành socket mới.

**Giới hạn của demo:** Đây là luồng TCP loopback có FIN được chủ động tạo, không phải mô phỏng mất Wi-Fi, máy chủ crash hoặc TCP RST. Trong môi trường không được phép mở listener loopback, có thể nhận `IOException`; không diễn giải lỗi môi trường đó thành sai lệch về hai cờ.

## 6. Tại sao điều kiện “`isConnected() && !isClosed()`” chỉ là kiểm tra sơ bộ?

Có thể dùng điều kiện này để từ chối những đối tượng **rõ ràng** chưa kết nối hoặc đã đóng cục bộ:

~~~java
// Fragment minh họa bên trong phương thức đã có Socket socket.
if (!socket.isConnected() || socket.isClosed()) {
    throw new IllegalStateException(
            "Socket was never connected or was locally closed");
}
~~~

Tuy nhiên, điều đó không tạo ra cam kết kết nối còn tốt. Ngay cả sau phép kiểm tra, peer có thể đóng/mất mạng, hoặc socket có thể được luồng khác đóng trước khi bạn gọi `write()`. Đây là một dạng **race giữa check và use**.

Các thao tác I/O cần được bao quanh bởi xử lý lỗi, không được giả định cờ boolean loại bỏ được `IOException`. Trạng thái của tài nguyên TCP và trạng thái ứng dụng là hai lớp khác nhau: một kết nối TCP có thể còn thiết lập, nhưng ứng dụng peer bị treo hoặc đã ngừng xử lý yêu cầu.

### Một mẫu kết nối, gửi và đọc có deadline rõ ràng

Đoạn dưới đây là **mẫu minh họa phương thức**, không phải ứng dụng chạy độc lập; `endpoint` là địa chỉ server đã kiểm soát và `request` là byte theo đúng giao thức mà server hiểu:

~~~java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;

// Mẫu cho giao thức minh họa chỉ phản hồi đúng một byte.
// Server phải được thiết kế để gửi một byte phản hồi như vậy.
static int requestOneByte(
        InetSocketAddress endpoint, byte[] request)
        throws IOException {

    try (Socket socket = new Socket()) {
        socket.connect(endpoint, 3_000); // Timeout TCP connect.
        socket.setSoTimeout(3_000);      // Timeout mỗi lần blocking read.

        socket.getOutputStream().write(request);

        int answer = socket.getInputStream().read();
        if (answer == -1) {
            throw new IOException(
                    "Peer ended its output before replying");
        }
        return answer;
    } catch (SocketTimeoutException ex) {
        // Không tự động có nghĩa peer đã đóng.
        throw new IOException(
                "Connect/read exceeded its deadline", ex);
    }
}
~~~

Mẫu này cần khai báo class/method chứa đoạn code và một server theo đúng giao thức một byte để chạy. `SocketTimeoutException` có thể xảy ra ở connect timeout hoặc read timeout (tùy bước). Đối với thao tác `read()`, Javadoc nói rằng khi `SO_TIMEOUT` xảy ra, socket vẫn có thể còn hợp lệ; mẫu minh họa vẫn đóng socket trong `try-with-resources` vì **chính sách ứng dụng** quyết định bỏ kết nối đã hết hạn.

**Phân biệt timeout:**

- `socket.connect(endpoint, 3000)`: giới hạn thời gian chờ thiết lập TCP.
- `socket.setSoTimeout(3000)`: giới hạn thời gian chờ các lần **blocking read** trên InputStream của socket; không phải đồng hồ đo “kết nối sống 3 giây”.
- `OutputStream.write(...)` không được bảo đảm có deadline do `SO_TIMEOUT` thiết lập. Nếu cần deadline cho cả request ở mức nghiệp vụ, phải thiết kế quản lý thời hạn tổng, cơ chế hủy/đóng kết nối và công nghệ I/O phù hợp.
- `SO_TIMEOUT=0` nghĩa là không giới hạn thời gian chờ đọc. Cân nhắc timeout dương cho dịch vụ cần tránh treo luồng.

## 7. Xác định khả năng trao đổi dữ liệu theo giao thức ứng dụng

Khi một hệ thống cần biết **peer có thể phục vụ yêu cầu ngay bây giờ hay không**, một mẫu tổng quát là:

~~~text
1) Kiểm tra socket chưa bị đóng cục bộ
2) Gửi request hoặc heartbeat đúng giao thức
3) Đọc phản hồi đúng framing với timeout
4) Xác nhận phản hồi có id / version / nội dung hợp lệ
5) Nếu EOF, timeout, I/O error hoặc response lỗi:
   đánh dấu connection không dùng lại, close và quyết định phục hồi
~~~

Tại bước 2, `write()` thành công **chỉ** cho thấy thao tác ghi của phía cục bộ không báo lỗi ngay. Bước 3–4 mới cung cấp bằng chứng ứng dụng bên kia đang phản hồi. Tuy vậy, phản hồi thành công cũng chỉ nói về **thời điểm đó**, không bảo đảm lần I/O kế tiếp thành công.

Với hệ thống dùng connection pool, trạng thái “khỏe” có thể phải xét cả tuổi kết nối, số lần lỗi, idle timeout phía server, tính hợp lệ của phiên đăng nhập và chính sách retry. Một pool không nên tự coi `isConnected=true` là tiêu chí duy nhất để tái sử dụng.

**Heartbeat và TCP keepalive khác nhau:**

- **Heartbeat ở tầng ứng dụng** gửi một thông điệp mà peer hiểu (ví dụ request/ping ứng dụng) và chờ ACK trong một deadline. Nó kiểm tra được việc **ứng dụng** có phản hồi theo hợp đồng giao thức.
- **TCP keepalive** có thể bật qua `socket.setKeepAlive(true)`, giúp hệ điều hành phát hiện một số kết nối chết sau thời gian nhàn rỗi. Thời gian probe/phát hiện do hệ điều hành/cấu hình quản lý; nó không phải API kiểm tra sức khỏe tức thời và không xác nhận server xử lý nghiệp vụ.
- Với yêu cầu lớn hoặc không thể xử lý lặp, phải áp dụng idempotency key/deduplication hoặc cơ chế xác nhận; retry sau timeout **không chứng minh request trước chưa được xử lý**.

## 8. Tình huống chẩn đoán thực tế

### Tình huống A — `isConnected=true`, `isClosed=false` nhưng ghi/đọc lỗi

Kiểm tra log `IOException`, thời điểm peer đóng kết nối, firewall/NAT idle timeout, heartbeat, trạng thái pool và deadline. Không gọi `connect()` lại trên cùng đối tượng socket đã hỏng hoặc đóng; tạo một `Socket` mới theo chính sách reconnect. Tránh vòng retry liên tục không giới hạn vì có thể tạo tải lớn và làm khó xác định nguyên nhân.

### Tình huống B — đọc `-1` nhưng `isClosed=false`

Peer có thể đã gửi FIN khi kết thúc chiều gửi; lúc đó Java đã đọc hết phần dữ liệu trước FIN. Xem giao thức có cho phép mình tiếp tục gửi hay không; nếu phiên giao tiếp hoàn tất, chủ động `close()` để giải phóng tài nguyên. Không chờ `isClosed` tự đổi thành `true` để quyết định hoàn tất.

### Tình huống C — không có dữ liệu, `available() == 0`

Không suy ra socket ngắt kết nối. Có thể server đang tính toán hoặc đang chờ request đầy đủ. Dùng framing có độ dài, delimiter hay giao thức rõ ràng; khi chờ phản hồi, đặt read timeout theo yêu cầu nghiệp vụ. Việc lặp `available()` theo vòng bận vừa tốn CPU vừa không giải quyết bài toán kiểm tra kết nối sống.

### Tình huống D — `write()` không lỗi nhưng phía bên kia không phản hồi

Byte có thể mới được xếp vào buffer; đường truyền có thể gặp sự cố chưa được phát hiện, hoặc server vẫn nhận nhưng đang chờ thêm dữ liệu. Kiểm tra ứng dụng có flush buffer tự tạo, có gửi đủ độ dài/terminator và có chờ đúng response không. Nếu request chỉ hoàn tất khi server gửi ACK, phải dựa vào ACK và deadline, không dựa vào `write()` hay cờ `isConnected`.

### Tình huống E — hai luồng cùng dùng một socket

Một luồng có thể gọi `close()` ngay sau khi luồng kia kiểm tra cờ. Khi đó thao tác I/O có thể ném `SocketException`. Thiết kế ownership/lifecycle rõ ràng, đồng bộ hóa đóng tài nguyên nếu cần và luôn xử lý lỗi I/O. Cặp `isConnected()/isClosed()` không tạo cơ chế khóa cho socket.

### Tình huống F — nhầm TCP FIN với TCP RST

FIN là kết thúc chiều gửi có trật tự: phần byte còn lại có thể đọc trước EOF. RST cho biết kết nối bị reset và có thể xuất hiện dưới dạng `SocketException`; thời điểm thấy lỗi phụ thuộc hệ điều hành, buffer và hoạt động I/O. Không dựa vào chuỗi thông báo ngoại lệ cụ thể để xây giao thức portable; bắt kiểu exception phù hợp và log ngữ cảnh.

## 9. Những ngộ nhận nên tránh

1. **“`isConnected=false` mới là mất mạng.”** Sai: socket đã kết nối vẫn có thể trả `true` sau khi peer mất mạng, thậm chí sau local `close()`.
2. **“`isClosed=false` nghĩa là socket còn tốt.”** Sai: nó chỉ cho biết phía Java cục bộ chưa đóng đối tượng.
3. **“Hai cờ cùng đúng là mâu thuẫn.”** Sai: `isConnected=true, isClosed=true` chính là trường hợp từng kết nối rồi đóng cục bộ.
4. **“EOF khiến `isClosed=true` ngay.”** Sai: một TCP FIN từ xa không gọi `Socket.close()` phía client.
5. **“`read()==-1` luôn có nghĩa peer vừa gửi FIN.”** Không đủ: chính chương trình cục bộ cũng có thể gọi `shutdownInput()`, và EOF có thể đến sau khi dữ liệu được đệm đã đọc hết.
6. **“`read()` timeout thì TCP chắc chắn chết.”** Sai: Javadoc bảo đảm timeout đọc được báo lỗi nhưng socket vẫn có thể hợp lệ; quyết định đóng/retry tùy chính sách.
7. **“`available()==0` là disconnected.”** Sai: giá trị đó không phải chỉ báo health.
8. **“`write()` thành công nghĩa là server đã xử lý.”** Sai: chỉ có phản hồi/ACK đúng giao thức mới hỗ trợ kết luận ở tầng ứng dụng.
9. **“TCP keepalive là heartbeat ứng dụng.”** Sai: keepalive kiểm tra ở tầng TCP theo lịch OS, không xác minh logic server.
10. **“Kiểm tra cờ trước khi I/O giúp khỏi cần catch `IOException`.”** Sai: tình trạng mạng hoặc socket có thể đổi ngay sau phép kiểm tra.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Mới tạo `Socket s = new Socket()`, `s.isClosed()` trả `false`. Có thể gọi `s.getOutputStream().write(...)` ngay không?  
**Đáp án:** Không. Socket chưa kết nối, `isConnected=false`. Cần `connect(...)` thành công trước.

**Câu 2.** Socket đã kết nối thành công rồi gọi `close()`. Hai cờ có giá trị nào?  
**Đáp án:** `isConnected=true` và `isClosed=true`. Lịch sử kết nối vẫn được ghi nhận.

**Câu 3.** Server gọi `shutdownOutput()` và client đọc được `-1`. Client có bắt buộc `isClosed=true` không?  
**Đáp án:** Không. FIN chỉ kết thúc chiều server gửi; client có thể vẫn `isClosed=false`.

**Câu 4.** Vì sao `socket.isConnected() && !socket.isClosed()` không phải health check?  
**Đáp án:** Hai cờ phản ánh kết nối từng thành công và trạng thái đóng cục bộ; chúng không truy vấn peer/đường mạng và có race với mọi I/O về sau.

**Câu 5.** Khi nào có thể khẳng định peer đã xử lý một request?  
**Đáp án:** Chỉ theo hợp đồng của giao thức ứng dụng, ví dụ nhận được ACK/response hợp lệ cho đúng request ID. `write()` thành công không đủ.

**Câu 6.** `setSoTimeout(3000)` ảnh hưởng thao tác nào?  
**Đáp án:** Thời gian chờ blocking `read()` trên input stream; không tự đặt timeout cho `connect()` hay `write()`. Muốn timeout của connect, dùng `connect(endpoint, timeout)`.

## Tài liệu đối chiếu

- Java SE 17 — `Socket`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html
- Java SE 17 — `InputStream.read()` và EOF: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html
- Java SE 17 — `SocketTimeoutException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketTimeoutException.html
- Java SE 17 — `ServerSocket`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- Java SE 17 — `SocketChannel` (để phân biệt ngữ nghĩa `isConnected`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html
