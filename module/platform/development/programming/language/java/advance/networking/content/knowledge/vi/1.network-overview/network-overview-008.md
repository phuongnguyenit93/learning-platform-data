# Kiến thức nền cần dùng khi lập trình mạng Java: luồng byte, bộ đệm, charset, ngoại lệ và xử lý đồng thời

## 1. Mục tiêu và bức tranh tổng thể

Lập trình mạng không chỉ là gọi `Socket` rồi gửi một `String`. Chương trình phải làm việc với **byte**, tự quy định ranh giới thông điệp, quản lý bộ đệm, thống nhất mã hóa ký tự, phản ứng đúng khi kết nối chậm/đứt và phối hợp nhiều tác vụ cùng lúc. Năm nhóm kiến thức này gắn chặt với nhau:

1. **Luồng byte** cho biết dữ liệu đi vào/đi ra như thế nào.
2. **Bộ đệm** ảnh hưởng đến số lần I/O, cách gom dữ liệu và xử lý gói đến từng phần.
3. **Charset** quy định cách chuyển văn bản thành byte và ngược lại.
4. **Ngoại lệ và thời hạn** giúp phân biệt kết thúc bình thường, dữ liệu hỏng, lỗi mạng và kết nối quá chậm.
5. **Xử lý đồng thời** cho phép phục vụ nhiều kết nối nhưng đòi hỏi quản lý tài nguyên, thứ tự và tải.

Sau bài này, bạn cần giải thích được vì sao một lần `read()` không tương ứng với một thông điệp; chọn được cách đóng khung dữ liệu; viết được giao thức văn bản UTF-8 hoặc frame nhị phân; và xử lý đúng EOF, timeout, đóng tài nguyên, nhiều kết nối đồng thời.

### 1.1. Phân biệt TCP, UDP và API đọc/ghi

- **TCP** cung cấp luồng byte **có thứ tự và đáng tin cậy trong khi kết nối hoạt động**. TCP không bảo tồn ranh giới các lần `write()`: một lần ghi có thể đến qua nhiều lần đọc; nhiều lần ghi có thể được đọc gộp. TCP cũng không tự bảo đảm phía ứng dụng đã xử lý thông điệp, không cứu được dữ liệu chưa xác nhận sau khi một đầu mất kết nối.
- **UDP** vận chuyển các datagram riêng biệt; mỗi lần nhận lấy dữ liệu của một datagram, nhưng datagram có thể mất, trùng, đến sai thứ tự hoặc bị cắt nếu bộ đệm nhận quá nhỏ. Java dùng `DatagramSocket`/`DatagramPacket` cho API truyền thống; các quy tắc đóng khung TCP bên dưới không tự động áp dụng cho UDP.
- **Java I/O** phân biệt `InputStream`/`OutputStream` (byte), `Reader`/`Writer` (ký tự), và các API NIO như `ByteBuffer`/`SocketChannel` (bộ đệm byte, có thể cấu hình non-blocking). Việc chọn API không thay thế thiết kế giao thức.

Ví dụ: bên gửi gọi `write("A")` rồi `write("BC")`. Bên nhận TCP có thể đọc được `"ABC"` một lần, `"A"` + `"BC"`, hoặc `"AB"` + `"C"`. Cả ba đều hợp lệ. Vì vậy, **giao thức ứng dụng** phải nói rõ một thông điệp kết thúc ở đâu.

## 2. Luồng byte: đọc, ghi, EOF và vòng đời kết nối

### 2.1. Những hợp đồng cần thuộc

| Thao tác | Ý nghĩa thực tế | Không được suy luận |
| --- | --- | --- |
| `in.read()` | Một byte (0–255), hoặc `-1` khi hết luồng | `-1` không phải là byte dữ liệu |
| `in.read(buf, off, len)` | Trả về số byte thực nhận; có thể ít hơn `len`; `-1` báo EOF | Không được mặc định đọc đủ `len` |
| `out.write(bytes)` | Gửi các byte vào luồng đầu ra; có thể bị chặn hoặc ném `IOException` | Lệnh hoàn thành không có nghĩa peer đã xử lý |
| `out.flush()` | Đẩy dữ liệu còn giữ trong tầng đệm Java xuống luồng phía dưới | Không bảo đảm peer đã nhận/ghi bền vững |
| `close()` | Đóng tài nguyên, thường làm kết nối socket không dùng tiếp được | Không thay thế việc trao đổi phản hồi ở tầng ứng dụng |

Với `InputStream`, `read(byte[])` thường chặn khi chưa có byte/EOF/lỗi. Một kết quả dương chỉ nói rằng **bấy nhiêu byte** đã sẵn sàng; phần còn lại của message có thể đến sau. Không dùng `available()` để đo tổng chiều dài thông điệp: nó chỉ ước lượng số byte có thể đọc ngay mà không chặn, và `0` không đồng nghĩa EOF.

Nếu cần **đúng N byte**, lặp cho đến khi đủ, hoặc dùng `DataInputStream.readFully(byte[])`. `InputStream.readNBytes(n)` có từ Java 9 nhưng có thể trả ít hơn `n` nếu EOF: người gọi vẫn phải kiểm tra độ dài. Tránh `readAllBytes()` trên kết nối sống lâu hoặc payload không giới hạn vì có thể chờ EOF và tiêu thụ nhiều bộ nhớ.

### 2.2. Vòng lặp đọc và việc đóng tài nguyên

Đoạn sau minh họa xử lý từng mẩu byte khi giao thức cho phép đọc đến EOF; hàm `consume` là xử lý ứng dụng do bạn tự cài đặt:

~~~java
byte[] buffer = new byte[4096];
int count;
while ((count = input.read(buffer)) != -1) {
    consume(buffer, 0, count); // Chỉ dùng count byte vừa đọc
}
~~~

Đây **không phải** khuôn mẫu nhận một message TCP thông thường: với kết nối giữ mở để trao đổi nhiều message, chờ EOF có thể làm cả hai phía chờ nhau vô hạn. Chỉ dùng kiểu đọc đến EOF khi giao thức thực sự lấy EOF làm ranh giới.

Với socket, nên đóng bằng `try-with-resources`. Đóng `Socket` cũng đóng các stream của nó. Nếu chỉ cần báo “tôi đã gửi xong” nhưng còn muốn nhận phản hồi, dùng `socket.shutdownOutput()` theo **quy ước giao thức**; đóng `OutputStream` bọc từ socket thường đóng cả socket và không thay thế half-close. `shutdownOutput()` báo EOF cho hướng gửi sau khi phần byte đã gửi xong, còn hướng nhận vẫn có thể hoạt động. Không dùng half-close như dấu kết thúc nếu giao thức của bạn dùng frame có độ dài và tái sử dụng kết nối.

Trong chương trình mạng, luôn hỏi: “Điều gì cho biết một message đã hoàn tất?” Câu trả lời hợp lệ có thể là newline, độ dài, một cấu trúc tự phân định, hoặc EOF theo hợp đồng rõ ràng; **không phải** số lần `read()`.

## 3. Bộ đệm: hiệu năng khác với ranh giới thông điệp

### 3.1. `BufferedInputStream` và `BufferedOutputStream`

Bộ đệm gom nhiều thao tác nhỏ thành ít lần truy cập tầng dưới hơn. Ví dụ, `BufferedOutputStream` có thể giữ byte trong RAM cho đến khi đầy hoặc gọi `flush()`. Khi bạn triển khai protocol yêu cầu phản hồi ngay, hãy `flush()` sau khi hoàn thành **frame**, nếu không hai phía có thể cùng chờ: server chờ byte của client, client chờ phản hồi của server trong khi request vẫn nằm ở bộ đệm.

Ngược lại, gọi `flush()` sau **mọi byte** có thể làm mất lợi ích của bộ đệm. Hãy chọn ranh giới flush theo thông điệp và yêu cầu độ trễ. `BufferedInputStream` có thể đọc sẵn nhiều byte hơn số logic ứng dụng vừa lấy; không mở thêm một Reader khác để đọc cạnh tranh trên cùng socket nếu không có thiết kế điều phối.

Bộ đệm tại ứng dụng, bộ đệm của hệ điều hành và buffer TCP là các tầng khác nhau. Chúng **không** tạo ranh giới message và cũng không thay thế kiểm tra độ dài payload.

### 3.2. `ByteBuffer` của NIO

`ByteBuffer` có ba mốc cần hiểu:

- `capacity`: sức chứa cố định.
- `position`: vị trí thao tác tiếp theo.
- `limit`: ranh giới đang được phép đọc/ghi.

Chu kỳ phổ biến khi đọc byte từ channel vào bộ đệm là **ghi vào buffer → `flip()` → đọc các byte hiện có → `compact()` → nhận thêm byte**. `flip()` đặt limit bằng vị trí ghi hiện tại rồi đưa position về 0. `compact()` chuyển các byte **chưa xử lý** về đầu để tiếp tục ghép frame. `clear()` chỉ đặt lại chỉ số và coi dữ liệu cũ là có thể ghi đè, không xóa vật lý và **không bảo tồn** một frame chưa hoàn chỉnh.

Ví dụ trạng thái:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(8);
buffer.put(new byte[] {10, 20, 30}); // position = 3
buffer.flip();                        // position = 0, limit = 3
int first = Byte.toUnsignedInt(buffer.get()); // 10
buffer.compact();                     // Giữ lại 20, 30; position = 2
~~~

Với `SocketChannel` ở chế độ non-blocking, `read()` có thể trả `0` khi hiện chưa có dữ liệu; `write()` cũng có thể ghi ít hơn số byte còn lại. Vì vậy cần quan sát `hasRemaining()`, duy trì trạng thái frame qua nhiều lần thao tác, và sử dụng `Selector`/event loop khi chọn mô hình này. Đừng bê nguyên giả định “một lần ghi là xong” của đoạn code blocking sang NIO.

## 4. Charset: chuỗi ký tự không phải chuỗi byte

### 4.1. Mã hóa nhất quán theo giao thức

`String` của Java biểu diễn văn bản dưới dạng các đơn vị UTF-16, còn dữ liệu trên dây là byte. Dùng charset được chỉ định tường minh, thông thường là `StandardCharsets.UTF_8`:

~~~java
byte[] wire = "Việt".getBytes(StandardCharsets.UTF_8);
System.out.println("Việt".length()); // 4 đơn vị UTF-16
System.out.println(wire.length);     // 6 byte UTF-8
String restored = new String(wire, StandardCharsets.UTF_8);
~~~

`String.length()`, số code point và số byte UTF-8 có thể khác nhau. Với emoji, một ký tự hiển thị có thể chiếm **hai** đơn vị UTF-16. Vì vậy header “độ dài payload” của giao thức nhị phân phải đếm **byte sau mã hóa**, không lấy `message.length()`.

Không dùng `new String(bytes)` hay `getBytes()` không tham số trong một giao thức cần chạy giống nhau giữa môi trường: chúng phụ thuộc charset mặc định của runtime. Với giao thức văn bản, hai phía phải đồng ý charset, ký tự phân cách dòng và cách xử lý byte lỗi.

### 4.2. Biên của chunk có thể cắt giữa ký tự đa byte

Một ký tự UTF-8 có thể trải qua nhiều lần `read()`. Nếu nhận từng chunk rồi gọi `new String(chunk, UTF_8)`, bạn có thể giải mã một ký tự khi mới nhận nửa số byte và tạo ký tự thay thế (�). Cách đúng là **ghép đủ một frame ở cấp byte rồi giải mã**, hoặc dùng `InputStreamReader`/`CharsetDecoder` duy trì trạng thái qua nhiều chunk.

- Với protocol theo dòng: `BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))` xử lý việc giải mã qua nhiều lần đọc, còn `readLine()` xác định ranh giới dựa trên newline và bỏ ký tự xuống dòng khỏi kết quả. Đừng trộn `BufferedReader` với `DataInputStream` đọc trực tiếp trên cùng socket: Reader có thể đọc trước byte của frame kế tiếp.
- Với frame có độ dài: đọc **đúng số byte payload**, sau đó giải mã đúng một lần. Muốn từ chối UTF-8 sai định dạng, dùng `StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)`. Bộ giải mã mặc định của một số API tiện lợi thay lỗi bằng ký tự thay thế; chọn chính sách rõ ràng thay vì vô tình bỏ qua dữ liệu hỏng.
- Với protocol dòng, quy định rõ `\n` hay `\r\n`, độ dài dòng tối đa và việc văn bản có được phép chứa newline hay không. Không dùng newline làm delimiter nếu payload có thể chứa newline tùy ý mà không có escaping.

**Lưu ý:** `DataOutputStream.writeUTF()` dùng “modified UTF-8” và prefix độ dài riêng của Java; nó không tương đương frame UTF-8 chuẩn tùy ý. Chỉ dùng nó khi hai phía chủ động thống nhất đúng định dạng đó.

## 5. Đóng khung message: quy tắc nối các kiến thức nền

Vì TCP chỉ có byte stream, hai đầu phải thống nhất **framing** trước khi trao đổi. Ba phương án thường gặp:

| Cách đóng khung | Khi phù hợp | Điều phải kiểm soát |
| --- | --- | --- |
| Delimiter như `\n` | Lệnh/dòng văn bản đơn giản | Escape newline bên trong dữ liệu, giới hạn chiều dài dòng, charset |
| Length prefix + payload | Frame nhị phân hoặc text tùy ý | Endianness, kích thước prefix, byte length, giới hạn tối đa, EOF giữa frame |
| Đóng kết nối/half-close sau payload | Giao thức một lần gửi rồi kết thúc | Không phù hợp với kết nối tái sử dụng/trao đổi qua lại không có thỏa thuận |

Một frame phổ biến là **[4 byte unsigned/signed length theo hợp đồng] + [N byte UTF-8]**. Ví dụ dưới đây dùng **số nguyên có dấu 32-bit, big-endian** theo `DataOutputStream.writeInt()` và chấp nhận `0 ≤ N ≤ 65_536`. Cách diễn giải length và giới hạn phải được tài liệu hóa để các client khác ngôn ngữ có thể tương tác.

Luồng nhận đúng là: **đọc đủ 4 byte length → kiểm tra length trước khi cấp phát → đọc đúng N byte → decode UTF-8 → xử lý message**. Nếu `readFully` không đủ byte do EOF, frame bị cắt giữa chừng và là lỗi protocol, không được im lặng coi như một message đầy đủ. Giới hạn frame giúp ngăn cấp phát bộ nhớ tùy ý từ length do peer cung cấp.

## 6. Ngoại lệ, timeout và giải phóng tài nguyên

### 6.1. Không đánh đồng mọi kết thúc với cùng một lỗi

| Hiện tượng | Tín hiệu Java thường gặp | Xử lý phù hợp |
| --- | --- | --- |
| Peer kết thúc bình thường tại ranh giới giao thức | `read() == -1` trước frame mới; đôi khi `EOFException` khi đọc prefix | Đóng phiên; phân biệt EOF hợp lệ với frame đang dở |
| Peer đóng giữa length/payload | `EOFException`, `IOException` | Báo frame không hoàn chỉnh, bỏ dữ liệu dở |
| Không có byte trong thời hạn đọc | `SocketTimeoutException` | Áp dụng deadline/chính sách timeout; không coi là EOF |
| Không kết nối được hoặc DNS lỗi | `ConnectException`, `UnknownHostException` | Báo đúng nguyên nhân, cân nhắc retry có giới hạn |
| Kết nối bị reset/đứt khi ghi hoặc đọc | `SocketException` hoặc `IOException` | Đóng kết nối, xác định tác vụ có thể retry an toàn hay không |
| Payload UTF-8 không hợp lệ với decoder strict | `CharacterCodingException` (một `IOException`) | Từ chối frame theo protocol, log thông tin an toàn |
| Future/task chờ bị ngắt | `InterruptedException` | Phục hồi cờ interrupt và thoát theo chính sách hủy |

**Timeout kết nối và timeout đọc khác nhau.** `Socket.connect(address, timeoutMillis)` giới hạn thời gian kết nối; `socket.setSoTimeout(timeoutMillis)` đặt timeout cho thao tác đọc blocking trên socket (và `ServerSocket.setSoTimeout` cho `accept()`). Nó **không** phải deadline end-to-end và không tự giới hạn mọi thao tác ghi. Với yêu cầu cần tổng thời gian tối đa, hãy thiết kế deadline riêng và cơ chế hủy/đóng socket.

Lệnh `flush()` thành công không xác nhận peer đã xử lý. Khi client gửi request rồi gặp timeout trước response, không thể mặc định server chưa thực hiện request. Retry có thể tạo hiệu ứng kép. Nếu nghiệp vụ có side effect, cần request ID, idempotency hoặc cơ chế xác nhận ở tầng ứng dụng.

### 6.2. Dọn dẹp và quan sát lỗi

- Mở tài nguyên gần nơi dùng, đóng bằng `try-with-resources` kể cả khi ném exception. Không “nuốt” `IOException` rồi tiếp tục dùng socket có trạng thái không rõ.
- Giữ nguyên nguyên nhân gốc và ngữ cảnh (địa chỉ, thao tác, frame/byte count, timeout), nhưng đừng log toàn bộ payload chứa dữ liệu nhạy cảm.
- Kiểm tra kích thước, checksum/format khi giao thức yêu cầu; giới hạn dữ liệu đầu vào trước cấp phát và trước chuyển sang các bước xử lý đắt tiền.
- Khi catch `InterruptedException` ở tác vụ cần hủy: gọi `Thread.currentThread().interrupt()` rồi thoát/đóng tài nguyên theo hợp đồng. Không giả định `interrupt()` luôn hủy được mọi socket I/O blocking của mọi API và nền tảng; đóng socket hoặc timeout là cơ chế quản lý thực tế.

## 7. Xử lý đồng thời: nhiều kết nối, một protocol rõ ràng

Một server blocking thường có luồng nhận kết nối (`accept()`) và trao socket đã chấp nhận cho worker. Các lựa chọn chính:

- **Thread cho mỗi kết nối**: dễ hiểu nhưng thread nền tảng, stack và chuyển ngữ cảnh có chi phí; rất nhiều client chậm có thể làm hết tài nguyên.
- **`ExecutorService` cố định** (Java 17+): khống chế số worker hoạt động đồng thời, nhưng `Executors.newFixedThreadPool` dùng hàng đợi không giới hạn theo mặc định; vẫn cần chính sách giới hạn số kết nối, timeout, queue/backpressure và từ chối tải.
- **Non-blocking NIO + `Selector`**: ít thread quản lý nhiều socket bằng trạng thái đọc/ghi riêng, đổi lại state machine frame và partial write phức tạp hơn.
- **Virtual threads** (Java 21+): `Executors.newVirtualThreadPerTaskExecutor()` làm mô hình blocking dễ mở rộng về chi phí thread, nhưng **không** miễn trừ giới hạn kết nối, bộ nhớ, CPU, database hay dịch vụ phụ thuộc. Đây là lựa chọn Java 21+, không phải API của Java 17.

**Quy tắc sở hữu:** mỗi kết nối nên có một luồng đọc được điều phối rõ ràng; nếu nhiều tác vụ cùng ghi một socket, phải serialize frame nguyên vẹn theo đúng thứ tự. Dùng một `DataOutputStream` từ nhiều thread mà không có lock/queue phù hợp có thể làm header/payload của các message xen kẽ. Không chia sẻ `ByteBuffer` có position mutable giữa worker mà không đồng bộ.

Luồng `accept()` không nên tự xử lý công việc lâu; worker cần timeout và giới hạn tải, và phải đóng socket khi nhiệm vụ lỗi/từ chối. Khi dừng server, ngừng nhận client mới, đóng listener, xử lý các kết nối đang hoạt động và chờ executor theo chính sách graceful shutdown. Tránh loop retry vô hạn ngay lập tức khi gặp lỗi I/O kéo dài.

## 8. Ví dụ Java 17+ chạy được: TCP echo theo frame độ dài

Ví dụ chạy hoàn toàn trên **loopback** của máy, không cần server bên ngoài. Server được chạy trên một worker; client gửi chuỗi tiếng Việt; cả hai trao đổi **[4 byte length, big-endian] + [UTF-8 payload]**. Bộ đệm được flush sau mỗi frame; `readFully()` gom đủ payload qua nhiều lần nhận; decoder strict phát hiện UTF-8 hỏng. Có giới hạn 64 KiB và timeout đọc để tránh chờ vô thời hạn.

Lưu vào file **FramedEchoDemo.java** (tên file phải khớp public class):

~~~java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FramedEchoDemo {
    private static final int MAX_FRAME_BYTES = 64 * 1024;

    private static void send(DataOutputStream out, String message)
            throws IOException {
        byte[] payload = message.getBytes(StandardCharsets.UTF_8);
        if (payload.length > MAX_FRAME_BYTES) {
            throw new IOException("Frame too large");
        }
        out.writeInt(payload.length); // 4 byte, big-endian
        out.write(payload);
        out.flush();                   // Đẩy cả frame qua buffer
    }

    private static String receive(DataInputStream in) throws IOException {
        int length = in.readInt();      // Chờ đủ 4 byte length
        if (length < 0 || length > MAX_FRAME_BYTES) {
            throw new IOException("Invalid frame length: " + length);
        }
        byte[] payload = new byte[length];
        in.readFully(payload);         // Chờ đủ length byte hoặc EOF
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(payload))
                .toString();
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket listener =
                     new ServerSocket(0, 1, InetAddress.getLoopbackAddress())) {
            listener.setSoTimeout(5_000);
            ExecutorService workers = Executors.newSingleThreadExecutor();
            try {
                Future<?> serverTask = workers.submit(() -> {
                    try (Socket peer = listener.accept();
                         DataInputStream in = new DataInputStream(
                                 new BufferedInputStream(peer.getInputStream()));
                         DataOutputStream out = new DataOutputStream(
                                 new BufferedOutputStream(peer.getOutputStream()))) {
                        peer.setSoTimeout(5_000);
                        String request = receive(in);
                        send(out, "ACK: " + request);
                    } catch (IOException error) {
                        throw new UncheckedIOException(error);
                    }
                });

                try (Socket client = new Socket(
                             InetAddress.getLoopbackAddress(),
                             listener.getLocalPort());
                     DataInputStream in = new DataInputStream(
                             new BufferedInputStream(client.getInputStream()));
                     DataOutputStream out = new DataOutputStream(
                             new BufferedOutputStream(client.getOutputStream()))) {
                    client.setSoTimeout(5_000);
                    send(out, "Xin chào mạng");
                    System.out.println(receive(in));
                }

                serverTask.get(); // Lấy cả exception của worker nếu có
            } finally {
                workers.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy trong thư mục chứa file:

~~~bash
javac -encoding UTF-8 FramedEchoDemo.java
java FramedEchoDemo
~~~

Stdout (khi terminal hỗ trợ hiển thị Unicode):

~~~text
ACK: Xin chào mạng
~~~

**Đọc đường đi của dữ liệu:**

1. `ServerSocket(0, ..., loopback)` chọn cổng cục bộ còn trống; server task chờ `accept()`, client kết nối đến đúng cổng đó.
2. Client mã hóa `"Xin chào mạng"` thành UTF-8; `send()` ghi độ dài **byte** rồi ghi payload. Flush đảm bảo byte không còn bị giữ trong `BufferedOutputStream`.
3. Server `readInt()` nhận prefix; kiểm tra `length` trước cấp phát; `readFully()` lặp ở tầng stream đến khi đủ byte, bất kể TCP chia dữ liệu thành bao nhiêu lần nhận.
4. Server giải mã UTF-8 strict, thêm tiền tố `"ACK: "`, gửi lại frame mới.
5. Client nhận đủ frame và in đúng một dòng. Các resource socket/stream đóng khi ra khỏi `try-with-resources`. `Future.get()` đưa exception của worker về main thay vì để lỗi bị che khuất.

Đây là **demo một kết nối, một request/response** nhằm chứng minh framing; không phải server sản xuất. Server thực tế cần vòng `accept` nhiều client, giới hạn kết nối và hàng đợi, xác thực nếu phù hợp, logging/metrics, chính sách retry và tắt dịch vụ có kiểm soát. Với một client chậm, timeout đọc cần được quyết định theo protocol; timeout ngắn trong demo chỉ để tránh chờ không giới hạn.

### 8.1. Tự kiểm chứng các ca lỗi quan trọng

- Đổi payload thành tiếng Việt có emoji: số byte UTF-8 có thể lớn hơn `String.length()`, nhưng kết quả vẫn đúng vì prefix lấy từ `payload.length`.
- Thử gửi frame có length âm hoặc lớn hơn 65.536: `receive()` từ chối **trước** cấp phát mảng.
- Gửi prefix length hợp lệ nhưng chỉ nửa payload rồi đóng socket: `readFully()` ném `EOFException`; không có message giả được trả về.
- Gửi frame dở và giữ socket mở: đọc có thể kết thúc bằng `SocketTimeoutException` sau thời gian chờ.
- Để peer gửi byte UTF-8 hỏng: decoder với `REPORT` ném `CharacterCodingException`. Nếu dùng `new String(payload, UTF_8)` thay thế, chính sách thông thường là thay byte lỗi, nên không bảo đảm phát hiện dữ liệu hỏng.
- Chia một frame qua nhiều `write()` hoặc gộp hai frame trong một `write()`: phía nhận vẫn phân tách đúng nếu lặp đọc theo length, chứng minh framing độc lập với chunk TCP.

## 9. Những lỗi phổ biến cần tránh

1. **Giả định một `write()` tương ứng một `read()`.** TCP là byte stream; phải có framing.
2. **Đọc một lần vào buffer rồi giải mã luôn.** Có thể chỉ nhận một phần frame hoặc nửa ký tự UTF-8.
3. **Ghi `String.length()` thành độ dài frame.** Phải đo byte sau khi mã hóa theo charset đã thống nhất.
4. **Dùng charset mặc định.** Có thể tạo dữ liệu khác nhau giữa runtime/máy; chọn UTF-8 tường minh.
5. **Quên `flush()` sau frame khi dùng buffered output.** Peer có thể chờ request chưa được đẩy xuống luồng.
6. **Dùng `available()` để quyết định đủ message.** Đây không phải API đọc toàn bộ dữ liệu.
7. **Không giới hạn length do client gửi.** Có thể gây cấp phát quá lớn hoặc treo chờ dữ liệu không bao giờ đến.
8. **Nhầm EOF, timeout và lỗi protocol.** Chúng đòi hỏi xử lý khác nhau; EOF giữa frame là frame hỏng.
9. **Đóng một stream rồi cố dùng stream còn lại của cùng socket.** Thường socket đã đóng; cần half-close hoặc thiết kế protocol thích hợp.
10. **Để nhiều worker ghi chung một socket không điều phối.** Có thể làm các frame xen kẽ và hỏng giao thức.
11. **Nghĩ rằng fixed thread pool đã khống chế tất cả tải.** Queue và số socket chờ vẫn cần giới hạn.
12. **Retry request sau timeout mà không xét idempotency.** Server có thể đã xử lý xong trước khi client thấy timeout.

## 10. Checklist khi bắt đầu một tính năng mạng

- [ ] Giao thức là TCP stream hay UDP datagram? Ranh giới thông điệp được xác định bằng gì?
- [ ] Độ dài là byte hay ký tự? Có prefix, thứ tự byte, giới hạn kích thước và chính sách frame lỗi?
- [ ] Charset có được chỉ định rõ (ví dụ UTF-8), và byte lỗi được báo hay thay thế?
- [ ] Mã có xử lý partial read/partial write đúng API, EOF giữa frame và buffer chưa xử lý?
- [ ] Thời hạn cho connect/read/accept và deadline nghiệp vụ có rõ ràng? Có đóng socket khi hủy/lỗi?
- [ ] Buffered output có flush tại ranh giới phù hợp? Có tránh đọc cạnh tranh giữa các wrapper?
- [ ] Ai sở hữu từng socket, buffer và luồng ghi? Số worker, kết nối, queue và tải phụ thuộc có giới hạn?
- [ ] Có test frame bị chia/gộp, payload Unicode, byte hỏng, length bất thường, timeout, reset và client đồng thời?

Nắm chắc các nguyên tắc này trước khi đi sâu vào NIO, HTTP, TLS hoặc các framework mạng sẽ giúp bạn suy luận đúng từ byte trên dây đến hành vi của một ứng dụng Java chạy đồng thời.