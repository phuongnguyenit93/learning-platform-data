# shutdownInput, shutdownOutput và đóng một chiều của kết nối TCP trong Java

**TCP là một kết nối full-duplex**: hai bên có thể đồng thời gửi và nhận byte trên cùng một socket. Nhưng một ứng dụng có thể đã gửi *hết* request mà vẫn cần nhận response. Nếu đóng toàn bộ socket ngay sau khi gửi, chiều nhận cũng bị đóng. **Socket.shutdownOutput()** giải quyết trường hợp này: kết thúc **chiều gửi local** mà vẫn giữ **chiều nhận local** để đọc dữ liệu từ peer.

Java còn có **Socket.shutdownInput()**, nhưng thao tác này hoàn toàn khác: nó chấm dứt việc **đọc ở local**, không gửi TCP FIN để bảo peer ngừng gửi. **Socket.close()** lại kết thúc sử dụng toàn bộ socket. Hiểu rõ ba thao tác là kiến thức cốt lõi của mục **TCP với Socket**.

Mục tiêu sau bài học: giải thích FIN và EOF trong TCP half-close; xác định chiều nào còn hoạt động sau mỗi lời gọi; viết chương trình Java 17 gửi request, shutdownOutput rồi nhận response; hiểu vì sao shutdownInput không đóng chiều gửi; và tránh lỗi mất dữ liệu, deadlock đợi EOF, đóng stream quá sớm, timeout và quản lý tài nguyên sai.

## 1. Một kết nối, hai hướng byte stream

~~~text
                TCP connection
CLIENT                                         SERVER
OutputStream  ----------------------------->  InputStream
InputStream   <-----------------------------  OutputStream
             hai hướng truyền độc lập
~~~

Đóng **chiều gửi** của client nghĩa là client không gửi byte mới nữa, còn server có thể tiếp tục trả response. Đóng **chiều nhận** của client nghĩa là client bỏ khả năng đọc dữ liệu server gửi, nhưng chiều client gửi tới server vẫn có thể mở.

**Half-close (đóng một chiều)** thường ám chỉ một bên ngừng *gửi* bằng FIN trong khi vẫn nhận được các byte của hướng còn lại. TCP FIN đi theo thứ tự của byte stream: peer đọc hết byte đã gửi trước FIN rồi thấy **EOF** (trong Java, nhiều lệnh đọc trả **-1**).

~~~text
CLIENT                                              SERVER
write(request) -----------------------------------> read(): byte của request
shutdownOutput() --------- FIN -------------------> read(): -1
[client đã kết thúc gửi nhưng vẫn đọc được]
               <----------------------------------- write(response)
read(): byte của response <------------------------
read(): -1 <----------- FIN ----------------------- shutdownOutput()
close()                                             close()
~~~

**FIN không phải ACK nghiệp vụ.** Việc Java trả về sau shutdownOutput không chứng minh peer đã xử lý request, ghi dữ liệu vào database hoặc gửi kết quả. Nếu cần biết tác vụ đã hoàn thành, cần **response** hoặc acknowledgment do tầng ứng dụng định nghĩa.

**EOF một chiều không có nghĩa cả TCP connection đã chết.** Khi server thấy EOF trên input, client vẫn có thể đang chờ server gửi response trên chiều ngược lại. Đây là lý do phân biệt half-close với close rất quan trọng.

## 2. So sánh shutdownOutput, shutdownInput và close

| Lời gọi trên java.net.Socket | Ảnh hưởng tại máy gọi | Tín hiệu/hiệu ứng ở peer | Chiều còn lại |
|---|---|---|---|
| **shutdownOutput()** | Dừng ghi; ghi tiếp gây IOException. TCP kết thúc hướng local → peer sau các byte đã gửi | Peer đọc hết byte cũ rồi nhận EOF (-1) khi FIN đến | **Input local vẫn có thể đọc** |
| **shutdownInput()** | Đặt input local vào EOF; read trên stream đã lấy trả -1; byte đến sau bị bỏ | Không gửi FIN để ra hiệu peer dừng gửi | **Output local vẫn có thể ghi** |
| **close()** | Đóng socket và các stream; không thể tái dùng socket | Peer có thể thấy EOF hoặc lỗi/reset tùy trạng thái và cách đóng | **Không còn I/O** |

### 2.1. Socket.shutdownOutput()

Hợp đồng của **Socket.shutdownOutput()**: với TCP, những dữ liệu đã được viết vào socket được gửi trước khi hướng gửi trải qua chuỗi đóng TCP bình thường. Sau đó **OutputStream.write(...)** tiếp sẽ ném **IOException**. Local **InputStream** vẫn được sử dụng để đọc response.

Đoạn minh họa sau giả định socket đã kết nối và requestBytes đã có sẵn (không phải chương trình chạy độc lập):

~~~java
socket.getOutputStream().write(requestBytes);
socket.shutdownOutput();        // Ngừng gửi local, đưa FIN theo sau dữ liệu.
byte[] reply = socket.getInputStream().readAllBytes();
// Khi protocol kết thúc, đóng socket để giải phóng tài nguyên.
~~~

**Một chiều đã shutdown không mở lại được trên cùng kết nối.** Nếu protocol muốn client gửi nhiều request liên tiếp, không gọi shutdownOutput sau request đầu tiên trừ khi protocol xác định rằng client vĩnh viễn không gửi tiếp.

### 2.2. Socket.shutdownInput()

**Socket.shutdownInput()** đặt input phía local ở trạng thái end-of-stream: với **InputStream đã lấy trước khi shutdown**, các lệnh read trả **-1**, còn available trả 0. Dữ liệu peer gửi tiếp đến hướng này sẽ được xác nhận rồi loại bỏ theo hợp đồng Socket.

~~~java
InputStream in = socket.getInputStream(); // Lấy trước khi shutdown.
socket.shutdownInput();
int eof = in.read();                     // -1.
~~~

**Chú ý:** **Socket.getInputStream()** có thể ném IOException nếu gọi *sau khi input đã shutdown*. Vì vậy không nên lấy stream mới sau shutdown rồi kỳ vọng chắc chắn nhận -1. Đoạn code ở trên cố ý lấy InputStream trước.

**shutdownInput không báo peer rằng client đã gửi xong.** Nếu server đang chờ EOF trên hướng client → server, client phải **shutdownOutput()**, không phải shutdownInput(). Phần lớn protocol request/response cần shutdownOutput nhiều hơn shutdownInput.

### 2.3. Socket.close()

**close()** đóng cả socket, InputStream và OutputStream; nó cũng đóng SocketChannel liên quan nếu có. Socket đã close không thể reconnect/rebind. Tùy trạng thái dữ liệu chưa đọc/chưa gửi, TCP và cấu hình như SO_LINGER, bên kia có thể quan sát EOF hoặc reset/lỗi; không được giả định mọi close đều tương đương một FIN bình thường mà ứng dụng đã xác nhận xong dữ liệu.

~~~java
try (Socket socket = new Socket(host, port)) {
    // Dùng stream hoặc half-close theo giao thức.
} // Tự động Socket.close() khi ra khỏi scope.
~~~

**Đóng stream lấy từ Socket cũng đóng cả socket.** Vì vậy **try-with-resources riêng cho OutputStream** là bẫy nếu sau đó bạn vẫn định đọc từ InputStream. Hãy để try-with-resources quản lý Socket ở phạm vi giao dịch, dùng shutdownOutput khi cần báo hết dữ liệu mà vẫn giữ chiều nhận.

## 3. EOF và message boundary: dùng đúng theo protocol

TCP chỉ cung cấp **dòng byte**, không bảo toàn ranh giới một lần write thành một lần read. Peer có thể đọc request qua nhiều lần read; các lần ghi cũng có thể được gộp lại.

Để biết một message kết thúc ở đâu, protocol cần quy tắc framing:

- **Length-prefix:** gửi độ dài trước rồi nhận đúng số byte đã khai báo.
- **Delimiter:** dùng ký hiệu phân cách (ví dụ newline), có kiểm soát escaping và giới hạn độ dài.
- **EOF-delimited:** toàn bộ payload của một hướng được xác định là kết thúc khi peer half-close/close hướng gửi. **shutdownOutput()** rất hữu ích cho kiểu này vì người gửi vẫn có thể đọc response.

Nếu server dùng **InputStream.readAllBytes()** để đợi EOF mà client không đóng chiều gửi, server sẽ chờ dữ liệu tiếp và có thể treo. Kiểu EOF-delimited cũng không phù hợp cho nhiều vòng request-response trên cùng chiều gửi, vì sau shutdownOutput không thể ghi request tiếp theo.

## 4. Ví dụ Java 17 hoàn chỉnh: gửi PING, đóng chiều gửi, nhận ACK

Protocol minh họa: client gửi UTF-8 **PING**, gọi shutdownOutput để server biết đã hết request; server đọc hết request đến EOF, gửi **ACK:PING**, rồi shutdownOutput để client biết hết response. Cả hai phía dùng try-with-resources để đóng socket sau khi trao đổi hoàn thành.

Ví dụ dùng loopback, cổng động do hệ điều hành cấp, không đòi hỏi máy chủ bên ngoài. Một worker thread cho phía server giúp hai bên chạy đồng thời. Main in toàn bộ kết quả sau khi kết thúc để stdout có thứ tự xác định.

Tệp **HalfCloseRoundTripDemo.java**:

~~~java
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class HalfCloseRoundTripDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket listener = new ServerSocket(0, 10, loopback)) {
            ExecutorService worker = Executors.newSingleThreadExecutor();
            try {
                Future<String> serverRead = worker.submit(() -> {
                    try (Socket peer = listener.accept()) {
                        peer.setSoTimeout(4_000);
                        String request = new String(
                                peer.getInputStream().readAllBytes(),
                                StandardCharsets.UTF_8);

                        byte[] response = ("ACK:" + request)
                                .getBytes(StandardCharsets.UTF_8);
                        peer.getOutputStream().write(response);
                        peer.shutdownOutput();
                        return request;
                    }
                });

                String reply;
                boolean clientOutputShutdown;

                try (Socket client = new Socket(
                        loopback, listener.getLocalPort())) {
                    client.setSoTimeout(4_000);
                    client.getOutputStream().write(
                            "PING".getBytes(StandardCharsets.UTF_8));
                    client.shutdownOutput();

                    clientOutputShutdown = client.isOutputShutdown();
                    reply = new String(
                            client.getInputStream().readAllBytes(),
                            StandardCharsets.UTF_8);
                }

                String requestAtServer =
                        serverRead.get(5, TimeUnit.SECONDS);
                System.out.println(
                        "Client output shutdown: " + clientOutputShutdown);
                System.out.println("Server received: " + requestAtServer);
                System.out.println("Client received: " + reply);
            } finally {
                worker.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file:

~~~bash
javac -encoding UTF-8 HalfCloseRoundTripDemo.java
java HalfCloseRoundTripDemo
~~~

Stdout của một lần chạy thành công:

~~~text
Client output shutdown: true
Server received: PING
Client received: ACK:PING
~~~

### Giải thích tuần tự

1. **ServerSocket** mở cổng loopback, **accept()** đợi kết nối trong worker. **Socket** do accept trả về là kết nối đã được thiết lập, khác với listener.
2. Client ghi **PING**, sau đó **shutdownOutput()**. Điều này báo hết request trong giao thức EOF-delimited. **isOutputShutdown()** thành true ở local.
3. Server **readAllBytes()** đọc toàn bộ request cho đến EOF do FIN bên client. Nó **không đợi socket client close hoàn toàn**. Sau đó server tạo reply.
4. Server gửi **ACK:PING**, gọi **shutdownOutput()**. Client vẫn đọc được vì mới dừng chiều gửi của mình chứ không dừng chiều nhận.
5. Client readAllBytes nhận response và đi đến EOF, rồi các socket lần lượt được đóng. **Future.get(...)** ở main lấy request server đã đọc để in kết quả theo thứ tự xác định.

Ví dụ nhỏ nên dùng **readAllBytes()**, nhưng trong ứng dụng thật phải giới hạn tổng kích thước input và deadline. **Socket.setSoTimeout(...)** giới hạn chờ cho các thao tác đọc blocking; nó **không** là deadline của toàn request và không tự giới hạn write hoặc connect. Nếu response rất lớn, nên đọc thành nhiều chunk và kiểm soát backpressure.

### Nếu client quên shutdownOutput thì sao?

Giữ nguyên server **readAllBytes()** nhưng bỏ **client.shutdownOutput()**:

~~~text
CLIENT                                  SERVER
write("PING")
readAllBytes(response) ---- chờ ----> readAllBytes(request) đang chờ EOF
                         (cả hai phía cùng chờ)
~~~

Server không biết request đã kết thúc nên chưa tạo ACK; client chờ ACK. Đây là **deadlock ở tầng giao thức**. Một phía có thể hết timeout hoặc đóng socket, nhưng phải sửa căn nguyên bằng framing rõ ràng hoặc client shutdownOutput theo quy ước EOF-delimited.

## 5. Ví dụ Java 17 hoàn chỉnh: shutdownInput chỉ tắt đọc ở local

Ví dụ sau khẳng định **shutdownInput** không cấm ghi. Client lấy InputStream trước, gọi shutdownInput rồi đọc được **-1**. Sau đó client vẫn gửi **HELLO**. Server đọc đủ dữ liệu vì chiều client → server còn hoạt động cho tới khi client shutdownOutput.

Tệp **ShutdownInputDemo.java**:

~~~java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ShutdownInputDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket listener = new ServerSocket(0, 10, loopback)) {
            ExecutorService worker = Executors.newSingleThreadExecutor();
            try {
                Future<String> received = worker.submit(() -> {
                    try (Socket peer = listener.accept()) {
                        peer.setSoTimeout(4_000);
                        return new String(
                                peer.getInputStream().readAllBytes(),
                                StandardCharsets.UTF_8);
                    }
                });

                boolean inputShutdown;
                int localRead;

                try (Socket client = new Socket(
                        loopback, listener.getLocalPort())) {
                    InputStream input = client.getInputStream();
                    client.shutdownInput();

                    inputShutdown = client.isInputShutdown();
                    localRead = input.read();  // -1 theo hợp đồng Socket.

                    client.getOutputStream().write(
                            "HELLO".getBytes(StandardCharsets.UTF_8));
                    client.shutdownOutput();
                }

                System.out.println(
                        "Client input shutdown: " + inputShutdown);
                System.out.println(
                        "Client read after shutdown: " + localRead);
                System.out.println(
                        "Server received: " + received.get(
                                5, TimeUnit.SECONDS));
            } finally {
                worker.shutdownNow();
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ShutdownInputDemo.java
java ShutdownInputDemo
~~~

Stdout khi chạy thành công:

~~~text
Client input shutdown: true
Client read after shutdown: -1
Server received: HELLO
~~~

Trong ví dụ, **server hoàn tất readAllBytes() nhờ client.shutdownOutput()**, chứ không phải client.shutdownInput(). Nếu chỉ shutdownInput mà không kết thúc chiều gửi, server vẫn có thể chờ EOF vô hạn.

Điểm dễ sai: nếu thay **InputStream input = client.getInputStream()** bằng lời gọi **client.getInputStream()** *sau* shutdownInput, Java Socket có thể ném **IOException**. Để minh họa local EOF cần giữ stream đã lấy từ trước.

## 6. Dùng BufferedOutputStream: flush trước khi half-close

Giả sử ứng dụng dùng buffer Java để giảm số lần ghi:

~~~java
BufferedOutputStream buffered =
        new BufferedOutputStream(socket.getOutputStream());
buffered.write(requestBytes);
buffered.flush();
socket.shutdownOutput();
byte[] response = socket.getInputStream().readAllBytes();
~~~

Đây là **đoạn minh họa**, giả định socket đã kết nối và requestBytes có sẵn; không phải chương trình hoàn chỉnh.

**Vì sao phải flush?** write lên BufferedOutputStream có thể mới đưa byte vào buffer trong tiến trình Java, chưa đưa byte vào SocketOutputStream. **shutdownOutput()** chỉ biết dữ liệu đã được chuyển vào tầng socket, không tự đi vào mọi wrapper buffer mà ứng dụng tạo. Cần **flush() trước khi shutdownOutput()**.

**Vì sao không buffered.close() ngay sau ghi?** Closing wrapper sẽ đóng output stream socket bên dưới và đóng luôn socket. Nếu còn cần đọc response, giữ socket sống, flush rồi shutdownOutput; cuối phiên đóng Socket bằng try-with-resources. Đừng dùng try-with-resources riêng cho wrapper output ở giữa một giao dịch half-close.

Cũng không được hiểu flush là peer đã xử lý: flush chuyển dữ liệu ra khỏi buffer ứng dụng theo hợp đồng stream; FIN báo hết chiều gửi; xác nhận thành công nghiệp vụ cần response phù hợp.

## 7. Phân biệt trạng thái local và tín hiệu từ peer

| Trạng thái/quan sát | Kết luận đúng | Kết luận sai cần tránh |
|---|---|---|
| **socket.isOutputShutdown()** là true | Local đã shutdown chiều gửi | Peer chắc chắn xử lý hết request |
| **socket.isInputShutdown()** là true | Local đã shutdown chiều nhận | Peer nhận được tín hiệu yêu cầu ngừng gửi |
| **socket.isClosed()** là true | Đối tượng socket local đã đóng | Remote chắc chắn thấy EOF bình thường |
| **socket.isConnected()** là true | Socket đã từng kết nối thành công | Kết nối hiện vẫn còn sống; ngay cả sau close có thể vẫn true |
| **input.read() == -1** | Đã đến EOF trên luồng đọc ấy | Không thể gửi response nữa qua chiều ngược |
| **input.available() == 0** | Ngay lúc ấy không có byte sẵn có theo API | Đã đến EOF; 0 không phải EOF |
| **IOException/SocketException** | Đã có lỗi I/O hoặc trạng thái không hợp lệ | Mọi lỗi đều là FIN bình thường của peer |

Nếu phía bạn gọi **shutdownInput()**, read của stream đã lấy trước trở về **-1** vì **quyết định local**. Nếu peer gọi **shutdownOutput()**, read cũng có thể tới **-1**, nhưng nguyên nhân là **FIN từ peer**. Phân biệt bằng flow protocol, log thời điểm shutdown và các cờ local; đừng dựa duy nhất vào giá trị -1.

Trong TCP, **FIN** chỉ kết thúc một hướng truyền bình thường. Khi có lỗi mạng, peer crash, đóng socket khi còn dữ liệu chưa xử lý hoặc SO_LINGER đặc biệt, có thể xuất hiện **RST** và exception thay vì EOF. Code phải xử lý cả đường thất bại và luôn dọn dẹp socket.

## 8. Half-close và close không thay thế quản lý tài nguyên

Sau shutdownOutput, socket vẫn chiếm tài nguyên; input có thể tiếp tục đọc, nhưng socket cần **close** khi giao thức đã hoàn tất. Nếu hai phía đã shutdownOutput và đều đọc thấy EOF, vẫn nên close để giải phóng tài nguyên local và làm rõ ownership.

**Không tái sử dụng chiều đã shutdown**: sau shutdownOutput, ghi tiếp lên Socket OutputStream ném IOException; sau shutdownInput, đọc trên InputStream đã lấy báo EOF. Không có phương thức undo để tiếp tục trao đổi hai chiều trên cùng connection.

**Không dùng close để mô phỏng shutdownOutput** nếu protocol yêu cầu response. Close sẽ chấm dứt cả khả năng nhận. Khi có yêu cầu gửi dữ liệu và chờ kết quả, hãy quy định chính xác ai gọi shutdownOutput lúc nào; sau khi nhận đủ response, mới close.

**ServerSocket.close()** đóng listener, khiến accept không tiếp tục chờ/nhận kết nối mới; nó không phải lời gọi half-close trên từng Socket đã accept. Trong code server thật, listener và các accepted socket có vòng đời riêng.

## 9. Với SocketChannel và các giao thức cao hơn

**java.nio.channels.SocketChannel** (Java NIO) có **shutdownInput()** và **shutdownOutput()** tương tự về ý nghĩa half-close, nhưng phương thức trả chính channel và hợp đồng NIO có chi tiết riêng:

- Sau **SocketChannel.shutdownInput()**, read tiếp trên channel cho **-1**; channel vẫn có thể mở để ghi.
- Sau **SocketChannel.shutdownOutput()**, write tiếp lên channel ném **ClosedChannelException** theo Java 17 API; không đồng nghĩa toàn bộ channel đã đóng.
- Nếu một thread đang chặn trong SocketChannel.read mà thread khác shutdown input, read có thể hoàn tất với **-1**. Shutdown output khi thread khác đang bị chặn trong write có thể khiến thread đó nhận **AsynchronousCloseException**.
- Với Selector/non-blocking NIO, còn phải quản lý SelectionKey, trạng thái half-close và buffer; không chỉ đơn giản gọi shutdown rồi bỏ qua event loop.

Không suy rằng **AsynchronousSocketChannel** có cùng mọi phương thức với SocketChannel. Hãy theo đúng API của loại channel thực sự đang dùng.

Ở tầng ứng dụng, **HTTP/1.1 keep-alive**, HTTP/2, WebSocket và các giao thức dùng framing riêng thường **không** coi EOF của toàn TCP connection là điểm kết thúc mỗi request. Đừng tự gọi shutdownOutput giữa các request trong một connection còn được tái sử dụng. **TLS/SSLSocket** có quy trình đóng riêng như close_notify; raw TCP FIN không thay thế ngữ nghĩa đóng an toàn của TLS. Khi dùng framework, tuân thủ lifecycle do framework và protocol quản lý.

## 10. Khi nào lựa chọn shutdownOutput, shutdownInput, close?

| Tình huống | Quyết định phù hợp |
|---|---|
| Client đã gửi hết payload theo protocol EOF-delimited nhưng cần nhận phản hồi | **Flush nếu có buffer, rồi shutdownOutput; vẫn đọc response** |
| Server dùng EOF để xác định request kết thúc | **Đọc đến -1 rồi xử lý và gửi response**, không mặc định đóng socket khi vừa nhận EOF |
| Local không còn muốn đọc dữ liệu đến nhưng vẫn có nhiệm vụ gửi | Cân nhắc **shutdownInput**, chấp nhận discard dữ liệu inbound |
| Muốn kết thúc hoàn toàn giao dịch, giải phóng tài nguyên | **Socket.close()** hoặc try-with-resources |
| Muốn dùng connection cho nhiều request/response | Chọn **length-prefix/delimiter** hoặc framing chuẩn, **không shutdownOutput sau request đầu** |
| Muốn ngắt read treo do peer không gửi FIN | Thiết lập **read timeout**, deadline, giới hạn byte và chính sách close |
| Muốn biết peer đã xử lý request hay chưa | Dùng **ack/response ở tầng ứng dụng**, không chỉ nhìn cờ shutdown |

### Những lỗi phổ biến

1. **Nhầm shutdownInput với shutdownOutput**: chỉ shutdownOutput báo hết chiều gửi để peer nhận EOF.
2. **Gọi close hoặc OutputStream.close quá sớm**: mất luôn khả năng đọc response.
3. **readAllBytes trên payload không giới hạn**: có thể làm đầy RAM hoặc đợi mãi; đặt quota, timeout, framing.
4. **Không flush buffer Java trước shutdownOutput**: byte nằm trong buffer có thể chưa đến socket.
5. **Hiểu EOF là cả connection đã đóng**: peer vẫn có thể gửi phản hồi theo chiều ngược.
6. **Tưởng shutdownOutput chứng minh server đã nhận/xử lý**: cần response nghiệp vụ.
7. **Tưởng isConnected là liveness check**: phương thức không chứng minh kết nối hiện còn hoạt động.
8. **Không xử lý RST, timeout, exception**: kết thúc lỗi khác với EOF bình thường.
9. **Không close sau khi half-close**: tài nguyên của socket chưa chắc được dọn.
10. **Không định nghĩa message framing**: một lần write không tương ứng một lần read.

## 11. Bài tập tự kiểm chứng

### Bài tập A — Tạo deadlock có kiểm soát

Trong **HalfCloseRoundTripDemo**, bỏ client.shutdownOutput nhưng giữ server readAllBytes và client đọc response. Dự đoán luồng nào chờ tại đâu. Dùng timeout để tránh treo vô hạn, rồi khôi phục shutdownOutput để chứng minh cơ chế EOF-delimited.

### Bài tập B — Lỗi đóng output stream

Thử sửa client để bọc **client.getOutputStream()** trong try-with-resources riêng, đóng stream trước khi đọc response. Giải thích vì sao socket bị đóng và vì sao **shutdownOutput()** mới là thao tác đúng nếu muốn giữ chiều nhận.

### Bài tập C — Trạng thái sau từng thao tác

Ghi các giá trị **isConnected**, **isInputShutdown**, **isOutputShutdown**, **isClosed** trước khi shutdown, sau shutdownOutput và sau close. Giải thích vì sao isConnected không thay đổi thành false chỉ vì socket đã close.

### Bài tập D — So sánh các kiểu framing

Thay readAllBytes bằng 4 byte length-prefix và payload có giới hạn 1 MB. Gửi hai request liên tiếp qua một TCP connection; khi nào cần shutdownOutput, và khi nào chỉ dùng độ dài để server biết message đã đủ?

### Bài tập E — Thử input shutdown

Chạy **ShutdownInputDemo**, giữ lại InputStream đã lấy trước và quan sát read() trả -1. Thử lấy InputStream **sau khi shutdownInput** và kiểm tra IOException. Giải thích tại sao shutdownInput không làm server readAllBytes kết thúc trước khi client shutdownOutput.

## 12. Câu hỏi kiểm tra hiểu đúng

**1. shutdownOutput có đóng chiều đọc local không?** Không. Đó là cơ sở để gửi request xong vẫn đọc response.

**2. read() == -1 ở server có nghĩa client không thể nhận response?** Không. Client có thể chỉ gửi FIN bằng shutdownOutput.

**3. shutdownInput có gửi TCP FIN tới peer không?** Không. Nó dừng đọc ở local; muốn báo hết byte chiều gửi phải gọi shutdownOutput.

**4. Vì sao không close OutputStream trước khi đọc response?** Đóng stream do Socket cung cấp đóng cả Socket, ngăn giao dịch tiếp tục.

**5. Vì sao readAllBytes có thể chặn?** Vì nó chờ EOF. Nếu peer không kết thúc chiều gửi hoặc không gửi thêm dữ liệu, thao tác có thể chờ đến timeout.

**6. Có thể gọi write sau shutdownOutput?** Không. Java Socket OutputStream sẽ ném IOException.

**7. Có cần close sau hai chiều đã kết thúc?** Có. Close dọn dẹp tài nguyên local và kết thúc vòng đời đối tượng Socket.

**8. FIN có nghĩa dữ liệu đã được xử lý thành công không?** Không. Đó là tín hiệu transport; xử lý nghiệp vụ cần xác nhận riêng.

## Tài liệu API đối chiếu

- Java SE 17, **Socket**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html
- Java SE 17, **SocketChannel**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html

**Ghi nhớ:** **shutdownOutput() kết thúc chiều gửi TCP và cho peer quan sát EOF sau các byte trước FIN; chiều nhận vẫn dùng được. shutdownInput() kết thúc đọc ở local và không thay peer gửi FIN. close() kết thúc sử dụng toàn bộ socket.** Half-close chỉ đúng khi protocol xác định ranh giới dữ liệu rõ ràng, bảo toàn buffer, xử lý lỗi/timeout và close sau khi giao dịch hoàn tất.