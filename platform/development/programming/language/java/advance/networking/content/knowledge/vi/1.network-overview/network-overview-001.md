# Lập trình mạng giải quyết bài toán trao đổi dữ liệu giữa các tiến trình như thế nào?

## 1. Bài toán: hai tiến trình không dùng chung bộ nhớ ứng dụng

Giả sử tiến trình A đang chạy giao diện đặt hàng, còn tiến trình B xử lý đơn hàng. A cần gửi yêu cầu “tạo đơn hàng”, B cần trả về mã đơn và trạng thái. Mỗi tiến trình có không gian địa chỉ riêng, vòng đời riêng, nên A không thể lấy trực tiếp một đối tượng Java đang nằm trong heap của B rồi gọi phương thức trên đối tượng đó như khi cả hai ở cùng một JVM.

**Lập trình mạng** giải quyết việc này bằng cách biến thông tin thành dữ liệu truyền qua một kênh giao tiếp đã thống nhất. Tiến trình gửi ghi dữ liệu vào một **socket**; hệ điều hành và ngăn xếp giao thức mạng chuyển dữ liệu đến socket của tiến trình nhận; tiến trình nhận đọc, giải mã, xử lý và có thể gửi phản hồi.

Đích có thể ở **cùng máy** (qua địa chỉ loopback) hoặc **máy khác** trong LAN/Internet. “Lập trình mạng” không đồng nghĩa với “gọi ra Internet”; trọng tâm là trao đổi thông điệp giữa các tiến trình thông qua các điểm cuối mạng.

Ví dụ luồng nghiệp vụ:

~~~text
Tiến trình A (client)                  Tiến trình B (server)
   yêu cầu tạo đơn ───── bytes ────────> đọc và giải mã
   chờ kết quả                           xử lý nghiệp vụ
   đọc và giải mã <───── bytes ───────── trả mã đơn/trạng thái
~~~

Điểm quan trọng: **đối tượng, lời gọi hàm và trạng thái bộ nhớ không tự đi qua mạng**. Hai bên trao đổi byte theo một định dạng/giao thức mà cả hai hiểu.

## 2. Những thành phần giúp tiến trình tìm và nói chuyện với nhau

| Thành phần | Vai trò |
| --- | --- |
| **Tiến trình** | Chương trình độc lập gửi hoặc nhận dữ liệu, ví dụ ứng dụng Java và dịch vụ xử lý đơn. |
| **Địa chỉ IP** | Xác định giao diện/đích ở tầng mạng; có thể là IPv4 hoặc IPv6. |
| **Cổng (port)** | Số nguyên trong khoảng 0–65535 giúp tầng vận chuyển chuyển dữ liệu đến đúng dịch vụ/socket trên máy đích. |
| **Giao thức vận chuyển** | TCP hoặc UDP quy định cách truyền byte/datagram và các bảo đảm liên quan. |
| **Socket** | Giao diện lập trình mà tiến trình dùng để kết nối, gửi và nhận dữ liệu qua hệ điều hành. |
| **Giao thức ứng dụng** | Quy ước ý nghĩa dữ liệu: lệnh gì, định dạng gì, lúc nào kết thúc thông điệp, phản hồi ra sao. |

Ví dụ dịch vụ TCP lắng nghe tại **127.0.0.1:5050**: 127.0.0.1 là IPv4 loopback (máy hiện tại), 5050 là cổng dịch vụ. Client kết nối đến địa chỉ đó. Trong TCP, một kết nối đang hoạt động được phân biệt bởi cặp địa chỉ IP và cổng của **hai đầu** cùng giao thức vận chuyển; nhiều client có thể kết nối đến cùng cổng lắng nghe nhờ các đầu bên client khác nhau.

Tên miền như api.example.com cần được phân giải thành địa chỉ IP (thường qua DNS) trước khi kết nối. Biết IP và port vẫn chưa đủ: đường mạng, firewall, server đang chạy và giao thức hai bên phải tương thích.

## 3. Dữ liệu đi từ tiến trình này sang tiến trình khác ra sao?

Nhìn theo trách nhiệm của từng lớp:

~~~text
Ứng dụng A
  dữ liệu nghiệp vụ -> mã hóa/đóng khung thành byte
      |
      v
  Socket API của hệ điều hành
      |
  TCP hoặc UDP (vận chuyển, port)
      |
  IP (địa chỉ và định tuyến)
      |
  mạng vật lý/ảo hoặc loopback
      |
  IP -> TCP hoặc UDP -> socket của B
      |
      v
Ứng dụng B
  đọc byte -> tách thông điệp -> giải mã -> xử lý
~~~

1. **Ứng dụng chuẩn bị nội dung:** một chuỗi, JSON, bản ghi nhị phân hoặc tài nguyên HTTP được mã hóa thành byte; Unicode nên có quy ước rõ ràng, thường là UTF-8.
2. **Ứng dụng ghi vào socket:** ví dụ Java dùng OutputStream. Việc gọi write hoặc flush chủ yếu chuyển dữ liệu qua các bộ đệm tương ứng; **không chứng minh bên nhận đã xử lý thành công**.
3. **Hệ điều hành vận chuyển:** TCP có thể chia/gộp dữ liệu thành nhiều segment; IP chuyển gói theo địa chỉ đích; mạng/loopback đưa tới hệ thống nhận.
4. **Hệ điều hành nhận và phân luồng:** tầng vận chuyển nhận diện socket theo địa chỉ, cổng, giao thức và trạng thái kết nối rồi đưa dữ liệu cho tiến trình có socket phù hợp.
5. **Ứng dụng nhận đọc và hiểu dữ liệu:** ví dụ đọc đủ một thông điệp, kiểm tra hợp lệ, thực hiện nghiệp vụ và gửi phản hồi.

Socket che bớt chi tiết thiết bị mạng, nhưng **không tự xác định cấu trúc và ý nghĩa của dữ liệu ứng dụng**. Hai chương trình vẫn phải thỏa thuận một giao thức.

## 4. Cơ chế client–server với TCP

**Server** mở cổng và chờ kết nối; **client** chủ động kết nối. Với Java blocking I/O, trình tự điển hình là:

1. Server tạo ServerSocket, **bind** vào địa chỉ/cổng và **listen**. Cổng phải chưa bị dịch vụ khác chiếm và phải được phép truy cập.
2. Server gọi accept(), chờ một client kết nối. accept() trả về **Socket mới cho kết nối đó**; ServerSocket vẫn là socket lắng nghe.
3. Client dùng Socket.connect(...) hướng tới địa chỉ/cổng của server. TCP thiết lập kết nối trước khi hai bên trao đổi byte ứng dụng.
4. Hai đầu lấy InputStream và OutputStream; mỗi đầu có thể vừa gửi vừa nhận (**full-duplex**).
5. Client gửi **một thông điệp hoàn chỉnh** theo quy ước, ví dụ chuỗi PING kết thúc bằng ký tự xuống dòng.
6. Server đọc đủ thông điệp, kiểm tra/diễn giải, xử lý rồi gửi PONG. Client đọc phản hồi.
7. Hai bên xử lý lỗi, kết thúc phiên và đóng tài nguyên. try-with-resources giúp đóng socket/stream khi rời phạm vi.

TCP cung cấp **luồng byte có thứ tự và truyền lại khi cần trong khi kết nối còn hoạt động**, cùng cơ chế điều khiển luồng và tắc nghẽn. Nhưng nó không biết “một đơn hàng” bắt đầu/kết thúc ở đâu và không thể bảo đảm giao dịch nghiệp vụ đã được commit. Kết nối có thể đứt giữa lúc gửi yêu cầu và nhận phản hồi, khiến client không biết server đã xử lý hay chưa.

## 5. Phân biệt byte stream với thông điệp

Đây là lỗi khái niệm rất thường gặp. Với TCP:

- Ghi 100 byte một lần **không có nghĩa** đầu nhận sẽ đọc được đúng 100 byte ở lần read() đầu tiên. Dữ liệu có thể tới từng phần hoặc nhiều lần ghi có thể được đọc gộp.
- read() có thể trả về ít byte hơn yêu cầu; khi stream kết thúc hợp lệ, read() trả -1. Vì vậy code đọc thông điệp phải lặp cho đến khi đủ byte hoặc có dấu kết thúc.
- Không nên dùng “đến lúc hết dữ liệu hiện có trong buffer” làm dấu kết thúc thông điệp; có thể vẫn còn dữ liệu đang trên đường.

Một **giao thức ứng dụng** thường chọn một trong các kiểu đóng khung:

| Cách đóng khung | Khi nào phù hợp | Rủi ro cần xử lý |
| --- | --- | --- |
| **Dấu phân cách** (ví dụ LF ở cuối dòng) | Lệnh văn bản ngắn như PING | Nội dung chứa LF phải được escape/giới hạn; áp giới hạn chiều dài dòng. |
| **Tiền tố độ dài** (ví dụ 4 byte length + payload) | JSON, dữ liệu nhị phân, giao thức riêng | Kiểm tra độ dài hợp lệ trước khi cấp phát/đọc; đọc chính xác đủ payload. |
| **Giao thức chuẩn** (HTTP, WebSocket, gRPC, ...) | API và hệ thống có nhiều bên tham gia | Tuân thủ framing, status, version, giới hạn và bảo mật của giao thức được chọn. |

Bên cạnh framing, hai bên cần thống nhất **mã hóa** (UTF-8), **cấu trúc** (ví dụ JSON), **ý nghĩa** (PING/PONG, yêu cầu/phản hồi), **phiên bản**, **xử lý lỗi**, và **giới hạn kích thước**. Ví dụ này dùng **một dòng UTF-8 cho một thông điệp** để thấy cơ chế rõ ràng.

## 6. Ví dụ Java 17+: hai tiến trình thật trao đổi qua TCP

Tạo hai tệp bên dưới trong cùng thư mục. Server chỉ bind vào **loopback** để thực hành an toàn trên một máy. Chương trình chỉ phục vụ **một** client rồi kết thúc, giúp tập trung vào luồng dữ liệu thay vì kiến trúc server đa kết nối.

**Tệp TcpServer.java**

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class TcpServer {
    private static final int PORT = 5050;

    public static void main(String[] args) throws IOException {
        try (ServerSocket listener =
                     new ServerSocket(PORT, 50, InetAddress.getLoopbackAddress())) {
            System.out.println("Server ready on port 5050 (loopback)");
            try (Socket socket = listener.accept()) {
                socket.setSoTimeout(5000);
                try (BufferedReader in = new BufferedReader(
                             new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8));
                     BufferedWriter out = new BufferedWriter(
                             new OutputStreamWriter(socket.getOutputStream(), StandardCharsets.UTF_8))) {
                    String request = in.readLine();
                    if (request == null) {
                        System.out.println("Client closed before sending a request");
                        return;
                    }
                    System.out.println("Server received: " + request);
                    String response = "PING".equals(request) ? "PONG" : "ERROR";
                    out.write(response);
                    out.newLine();
                    out.flush();
                    System.out.println("Server replied: " + response);
                }
            }
        }
    }
}
~~~

**Tệp TcpClient.java**

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class TcpClient {
    public static void main(String[] args) throws IOException {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(InetAddress.getLoopbackAddress(), 5050), 3000);
            socket.setSoTimeout(5000);
            try (BufferedReader in = new BufferedReader(
                         new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8));
                 BufferedWriter out = new BufferedWriter(
                         new OutputStreamWriter(socket.getOutputStream(), StandardCharsets.UTF_8))) {
                out.write("PING");
                out.newLine();
                out.flush();
                System.out.println("Client sent: PING");
                String response = in.readLine();
                if (response == null) {
                    throw new EOFException("Server closed without a response");
                }
                System.out.println("Client received: " + response);
            }
        }
    }
}
~~~

**Biên dịch và chạy** (cần JDK 17 hoặc mới hơn):

~~~sh
javac --release 17 -encoding UTF-8 TcpServer.java TcpClient.java
~~~

Ở terminal 1, chạy trước:

~~~sh
java TcpServer
~~~

Trong lúc server đang đợi tại accept(), mở terminal 2 và chạy:

~~~sh
java TcpClient
~~~

**Stdout mong đợi, terminal server:**

~~~text
Server ready on port 5050 (loopback)
Server received: PING
Server replied: PONG
~~~

**Stdout mong đợi, terminal client:**

~~~text
Client sent: PING
Client received: PONG
~~~

Các dòng của hai terminal có thể xen kẽ theo lịch chạy hệ điều hành, nhưng **thứ tự bên trong từng terminal** ở lần chạy thành công như trên. Mẫu này đã được kiểm tra biên dịch với chế độ Java 17 và chạy trao đổi PING/PONG thành công.

**Giải thích chính xác những gì vừa diễn ra:**

- new ServerSocket(..., InetAddress.getLoopbackAddress()) mở cổng 5050 chỉ trên địa chỉ loopback. Truy cập từ máy khác không được phép qua điểm bind này.
- accept() trả Socket của phiên client; client kết nối bằng InetSocketAddress cùng địa chỉ/port. Hai tiến trình độc lập có thể chạy ở hai JVM/terminal.
- OutputStreamWriter mã hóa ký tự thành UTF-8; BufferedWriter giữ dữ liệu trước khi flush(). Dòng newLine() là dấu phân cách; readLine() đọc đến hết dòng và bỏ dấu kết thúc dòng.
- Server nhận PING, áp dụng quy tắc ứng dụng và gửi PONG. TCP chuyển byte, còn **chương trình Java quyết định PING và PONG có ý nghĩa gì**.
- connect(..., 3000) đặt thời gian chờ kết nối tối đa 3 giây; setSoTimeout(5000) giới hạn thời gian chặn của thao tác đọc trên socket 5 giây. Chúng **không** tự giới hạn toàn bộ thời gian thực thi hay thời gian chờ tại ServerSocket.accept().
- Đóng stream/socket bằng try-with-resources giải phóng tài nguyên. Trong demo, server ngừng sau một kết nối và không tự khởi động lại.

Nếu xuất hiện BindException, có thể cổng 5050 đã có tiến trình dùng; đổi **cùng một số port** trong cả hai tệp. Nếu ConnectException xảy ra, hãy kiểm tra server đã chạy và địa chỉ/cổng khớp. Nếu client chạy trước server, kết nối có thể bị từ chối; đó không phải lỗi của cú pháp Java.

## 7. TCP và UDP: hai lựa chọn vận chuyển khác nhau

| Tiêu chí | TCP | UDP |
| --- | --- | --- |
| Kiểu trao đổi | Kết nối, **luồng byte** liên tục | **Datagram** độc lập, giữ ranh giới từng datagram ở API |
| Đảm bảo ở tầng vận chuyển | Byte nhận theo thứ tự, không lặp trong luồng khi kết nối còn hoạt động | Không bảo đảm datagram đến nơi, đúng thứ tự hay chỉ đến một lần |
| Khởi tạo | Phải thiết lập kết nối | Không cần bắt tay thiết lập kết nối kiểu TCP |
| Chi phí/trễ | Có bắt tay, trạng thái kết nối và cơ chế kiểm soát | Gửi datagram đơn giản hơn; không có nghĩa lúc nào cũng nhanh hơn trong mọi điều kiện |
| API Java tiêu biểu | Socket, ServerSocket; SocketChannel, ServerSocketChannel | DatagramSocket/DatagramPacket; DatagramChannel |
| Ví dụ thường gặp | API giao dịch, truyền tệp, HTTP/1.1 và HTTP/2 qua TCP | DNS truyền thống, một số luồng thời gian thực, khám phá dịch vụ |

**UDP không phải “TCP kém tin cậy” cho mọi trường hợp**: nó hữu ích khi ứng dụng muốn chủ động kiểm soát mất gói, thứ tự hoặc ưu tiên độ trễ. Tuy nhiên, nếu nghiệp vụ cần bảo đảm giao nhận và xử lý, ứng dụng phải tự xây cơ chế phù hợp hoặc sử dụng giao thức/thư viện cấp cao đã có.

Lưu ý: HTTP/3 dùng QUIC chạy trên UDP nhưng QUIC tự triển khai những cơ chế bảo đảm cần thiết ở tầng phía trên; vì vậy không suy ra HTTP/3 mất tin cậy chỉ vì nền tảng là UDP.

## 8. Tại sao thường dùng HTTP thay vì tự xây giao thức socket?

Các lớp ở Java tương ứng với các mức trừu tượng:

- **java.net.Socket / ServerSocket**: thao tác TCP ở mức byte stream; ứng dụng tự thiết kế thông điệp, framing và vòng đời phiên.
- **java.net.DatagramSocket**: gửi/nhận UDP datagram, ứng dụng tự quy định cách giải mã/xử lý.
- **java.nio.channels**: các API channel/buffer, hỗ trợ mô hình non-blocking với Selector khi cần quản lý nhiều kết nối.
- **java.net.http.HttpClient** (Java 11+): ứng dụng gửi HTTP request và nhận response ở mức HTTP, bao gồm URI, header, status code, body; có API đồng bộ và bất đồng bộ.
- **Framework phía server**: ví dụ Spring Web triển khai tầng HTTP, routing, xử lý dữ liệu và vòng đời request để code nghiệp vụ không phải trực tiếp đọc từng byte TCP.

Khi xây REST API thông thường, **HTTP/HTTPS** giúp hai phía dùng sẵn quy ước request/response, status, content type và công cụ vận hành. Khi phải thiết kế giao thức nhị phân riêng, thiết bị chuyên dụng hoặc cần hiểu sâu luồng dữ liệu, socket cấp thấp trở nên có ích. Không nên mặc định “tự viết TCP protocol” sẽ tốt hơn dùng chuẩn sẵn có.

## 9. Những tình huống lỗi mà ứng dụng thực tế phải giải quyết

**Lỗi định vị/kết nối:** sai DNS, sai IP/port, server chưa listen, firewall chặn, hết cổng/tài nguyên, hoặc không có route. Một client cần báo lỗi rõ ràng và quyết định retry hay thất bại.

**Đợi vô hạn:** connect(), accept() và read() có thể chặn ở những thời điểm khác nhau. Đặt **connect timeout**, **read timeout**, deadline cho yêu cầu và quản lý hủy tác vụ. Timeout không chứng minh server chưa thực hiện yêu cầu.

**Đóng kết nối sớm:** readLine() trả null khi đã gặp EOF trước bất kỳ ký tự nào của dòng kế tiếp. Với giao thức nhị phân cần đọc đủ length đã công bố và xử lý EOF giữa thông điệp như lỗi dữ liệu không hoàn chỉnh.

**Phản hồi không rõ:** client gửi lệnh “trừ tiền”, kết nối đứt trước phản hồi. Retry mù có thể thực hiện hai lần. Với nghiệp vụ có tác dụng phụ, thiết kế **idempotency key/request ID**, lưu vết và đối soát trạng thái thay vì lấy TCP làm bằng chứng duy nhất.

**Dữ liệu không tin cậy:** đối tác có thể gửi payload quá lớn, sai cú pháp, dữ liệu lạ hoặc nhiều thông điệp bất thường. Giới hạn kích thước, thời gian xử lý, số kết nối; xác thực/ủy quyền và kiểm tra dữ liệu trước khi dùng.

**Bảo mật:** TCP thường là luồng byte không mã hóa. Truyền thông nhạy cảm qua mạng cần TLS (HTTPS, SSLSocket/SSLServerSocket hoặc thư viện hỗ trợ TLS), kiểm tra chứng chỉ/tên máy chủ phù hợp; không gửi bí mật qua giao thức tùy biến không có bảo vệ.

**Nhiều client đồng thời:** ví dụ trên phục vụ một client. Server thực tế thường lặp accept(), giao việc cho ExecutorService/thread pool hoặc mô hình non-blocking; đặt giới hạn tải, hàng đợi và backpressure. Mở vô hạn thread hoặc giữ socket không timeout có thể làm cạn tài nguyên.

## 10. Các hiểu nhầm thường gặp

1. **“Hai JVM khác nhau có thể truyền nguyên object qua Socket.”** Không trực tiếp. Object phải được mã hóa thành dữ liệu thống nhất (ví dụ JSON/Protobuf), truyền byte và dựng lại ở đầu kia. Java native serialization không nên là mặc định cho dữ liệu không tin cậy.
2. **“Một lần write tương ứng một lần read.”** Sai với TCP: đây là byte stream, nên phải tự đóng khung và đọc đủ thông điệp.
3. **“flush() nghĩa là server đã nhận hoặc xử lý xong.”** Sai: flush đẩy dữ liệu khỏi buffer của writer; muốn xác nhận xử lý cần phản hồi ứng dụng/thiết kế giao dịch.
4. **“TCP luôn giao được mọi yêu cầu.”** TCP hỗ trợ truyền byte tin cậy khi kết nối hoạt động, nhưng không loại bỏ sự cố mạng, mất kết nối hoặc trạng thái nghiệp vụ không chắc chắn.
5. **“Có địa chỉ IP là đủ.”** Bên gửi còn cần port, giao thức đúng và quy tắc ứng dụng; tên miền, NAT, firewall hoặc bind chỉ ở loopback đều ảnh hưởng khả năng kết nối.
6. **“Socket chỉ dùng khi hai máy khác nhau.”** Hai tiến trình trên cùng máy cũng trao đổi qua TCP/UDP loopback; ngoài socket mạng còn có nhiều cơ chế IPC khác như pipe hoặc shared memory, tùy hệ điều hành.

## 11. Tự kiểm tra hiểu biết

- Nếu client gửi liên tiếp hai chuỗi, mỗi chuỗi 5 byte, server gọi read() một lần với buffer 10 byte, server **có chắc nhận được 10 byte không**? Không. Phải đọc lặp và có giao thức xác định hai thông điệp.
- Nếu client nhận được PONG thì biết được điều gì? Biết ứng dụng server đã đọc được PING và thực hiện nhánh trả lời PONG trong lần chạy này; không có nghĩa mọi thao tác nghiệp vụ khác đã commit nếu giao thức không nói như vậy.
- Nếu muốn đưa demo lên hai máy, cần đổi gì? Bind server vào địa chỉ mạng được phép, client dùng địa chỉ/hostname của server, cấu hình firewall/routing và TLS/xác thực thích hợp; không dùng loopback làm đích giữa hai máy.
- Nếu cần gửi JSON nhiều dòng qua TCP, có thể dùng readLine() một lần cho toàn JSON không? Không nên. Hãy chọn framing rõ ràng như length-prefix hoặc giao thức HTTP có quy định riêng.

## Kết luận

Lập trình mạng nối các tiến trình tách biệt bằng **socket + địa chỉ/cổng + giao thức vận chuyển + hợp đồng thông điệp ứng dụng**. Hệ điều hành lo chuyển byte/datagram giữa các đầu, còn ứng dụng chịu trách nhiệm tạo dữ liệu, phân ranh giới thông điệp, diễn giải ý nghĩa, xử lý lỗi, timeout và bảo mật. Hiểu rõ sự phân chia trách nhiệm này là nền tảng để học Socket, HTTP, dịch vụ phân tán và lập trình bất đồng bộ.

### Tài liệu tham khảo

- [Java 17 – Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): client TCP socket và các API kết nối/I/O.
- [Java 17 – ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): lắng nghe và chấp nhận kết nối TCP.
- [Java 17 – DatagramSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramSocket.html): giao tiếp bằng UDP datagram.
- [Java 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): giao tiếp ứng dụng ở tầng HTTP.
