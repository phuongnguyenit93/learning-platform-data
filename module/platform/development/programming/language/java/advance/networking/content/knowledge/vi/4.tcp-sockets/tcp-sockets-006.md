# Đọc chưa đủ dữ liệu, chờ vô hạn và ý nghĩa của giá trị `-1` khi đọc TCP Socket trong Java

## 1. Vấn đề thực sự: TCP là một luồng byte, không phải luồng “gói thông điệp”

Khi dùng `java.net.Socket` trong Java, chương trình lấy `InputStream` từ `socket.getInputStream()` để đọc dữ liệu TCP. Một lệnh `read(...)` **không hứa nhận đủ một message của ứng dụng**, ngay cả khi bên gửi vừa gọi `write(...)` một lần với toàn bộ message. TCP bảo toàn **thứ tự byte** trên một kết nối đang hoạt động và cung cấp cơ chế vận chuyển tin cậy, nhưng **không bảo toàn ranh giới các lần `write`/`read`**.

Ba trạng thái cần phân biệt:

1. **Có dữ liệu nhưng chưa đủ:** `read(buffer)` trả về số byte dương nhỏ hơn `buffer.length`. Đây là kết quả hợp lệ, thường gặp.
2. **Tạm thời chưa có byte nào, đầu gửi vẫn giữ luồng mở:** một lệnh đọc **blocking** có độ dài dương sẽ chờ dữ liệu, EOF hoặc lỗi. Nếu không cấu hình read timeout, chương trình có thể chờ rất lâu, về mặt cấu hình là không giới hạn thời gian.
3. **Đã đến cuối luồng đọc:** `InputStream.read(...)` trả **`-1`** khi đầu gửi đã kết thúc chiều gửi một cách cho phép phía nhận quan sát EOF và mọi byte đã nhận trước đó đều đã được tiêu thụ.

**Không được đánh đồng:** “hiện chưa có byte” ≠ “không còn byte nào nữa” ≠ “đã nhận đủ bản tin”. TCP tự nó không biết kích thước bản tin ứng dụng mà bạn đang chờ.

## 2. Giá trị trả về của các hàm đọc

Với `InputStream input = socket.getInputStream()` của một `Socket` TCP kiểu blocking:

| API | Giá trị đọc được | Khi đầu kia chưa gửi thêm nhưng chưa đóng chiều gửi | Khi hết luồng |
|---|---|---|---|
| `input.read()` | `0..255`: **giá trị của một byte** | Chờ; có thể timeout hoặc lỗi | `-1` |
| `input.read(buffer)`, với `buffer.length > 0` | `1..buffer.length`: **số byte thực nhận** | Chờ; có thể timeout hoặc lỗi | `-1` |
| `input.read(buffer, off, len)`, với `len > 0` | `1..len`: **số byte thực nhận** | Chờ; có thể timeout hoặc lỗi | `-1` |
| `input.read(buffer, off, 0)` | `0`, vì đã yêu cầu đọc **0 byte** | Trả ngay, không đợi mạng | `0` |
| `input.readNBytes(n)` (Java 11+) | `byte[]` dài không quá `n`; cố đọc đến đủ `n`/EOF/lỗi | Có thể chờ đến khi đủ/EOF/timeout | Có thể trả mảng ngắn hơn `n` |
| `new DataInputStream(input).readFully(buffer)` | Không trả về `int`; chỉ kết thúc thành công khi đủ số byte cần | Chờ đến đủ/EOF/lỗi | Ném `EOFException` nếu thiếu byte |

**Hai điểm dễ gây bug:**

- `input.read() == 0` **không phải** “chưa có dữ liệu”: nó nghĩa là byte `0x00` vừa được đọc. Chỉ `read(buffer, off, 0) == 0` là trường hợp độ dài yêu cầu bằng 0.
- Giá trị `-1` là **dấu hiệu kết thúc stream**, không phải số byte âm đã đọc, không phải mã trạng thái HTTP, không phải “đang chờ”, và không phải tín hiệu timeout.

Khi `read(buffer, off, len)` trả `n > 0`, chỉ vùng `buffer[off]` đến `buffer[off+n-1]` vừa được ghi bằng dữ liệu đọc. Phần còn lại của mảng **không được coi là dữ liệu hợp lệ mới nhận**. `read()` khác `read(buffer)` ở chỗ nó trả **giá trị byte** chứ không phải **số byte**.

### Ví dụ ngắn về số byte thực tế

Giả sử ứng dụng định nghĩa bản tin là năm byte ASCII `HELLO`, phía gửi viết một lần:

~~~java
output.write("HELLO".getBytes(java.nio.charset.StandardCharsets.US_ASCII));
output.flush();
~~~

Bên nhận dùng mảng 1024 byte:

~~~java
byte[] buffer = new byte[1024];
int count = input.read(buffer);
~~~

`count` có thể là **1, 2, 3, 4 hoặc 5** khi đúng năm byte đó tới mà chưa có dữ liệu khác; nếu còn byte của bản tin tiếp theo trong luồng, lần đọc cũng có thể nhận **nhiều hơn năm**. Không được hard-code rằng `count == 5` hoặc một lần đọc tương ứng đúng một lần `write`.

Lệnh `flush()` yêu cầu đẩy dữ liệu qua các tầng đệm phía ứng dụng; nó **không tạo ranh giới message của TCP** và không bảo đảm bên nhận đã xử lý đủ dữ liệu.

## 3. Tại sao có thể đọc thiếu hoặc chờ mãi?

Trình tự điển hình:

~~~text
Client gửi:    [H E] .......... [L L O] .......... (vẫn giữ TCP mở)
Server đọc:    read(buf) → 2   read(buf) → 3   read(buf) → CHỜ
Ứng dụng cần: [H E L L O]  (đủ 5 byte)
~~~

Các byte có thể được chia hoặc gộp khác nhau do lập lịch tiến trình, bộ đệm TCP, mạng, kích thước cửa sổ và cách hệ điều hành bàn giao byte cho Java. **Không nên dự đoán số byte của từng lần đọc** từ số packet hay số lần `write`.

Một số kiểu treo thường gặp:

- **Không có quy tắc xác định kết thúc bản tin:** bên gửi giữ kết nối để tái sử dụng, bên nhận chờ EOF để biết “gửi xong”; hai bên không thể tiến lên.
- **Hai bên cùng chờ:** client đợi response; server đợi thêm byte hoặc delimiter chưa được client gửi.
- **Sai kích thước/encoding:** header nói body có 100 byte nhưng chỉ có 20 byte, hoặc tính độ dài ký tự UTF-8 thay vì độ dài byte thực gửi.
- **Thiếu newline:** bên nhận gọi `BufferedReader.readLine()`, bên gửi viết text không có dấu kết thúc dòng, cũng không đóng chiều gửi; `readLine()` tiếp tục chờ.
- **Sử dụng API “đọc hết luồng”:** `readAllBytes()` chờ EOF, nên không phù hợp để nhận một message trên kết nối duy trì lâu dài nếu protocol không đóng sau message.

Không có một lần `read` nào tự định nghĩa “xong bản tin”: đây là nhiệm vụ của **application protocol**.

## 4. Chờ vô hạn và `Socket.setSoTimeout`

`Socket` TCP mặc định dùng **blocking I/O** với `SO_TIMEOUT = 0`. Với một lời gọi `read` cần byte dữ liệu, `0` nghĩa là **không có giới hạn thời gian chờ đọc do `SO_TIMEOUT` áp đặt**. Lệnh vẫn có thể kết thúc vì data, EOF hoặc `IOException` do lỗi mạng/đóng socket; “vô hạn” không hứa kết nối thực sự sống mãi.

~~~java
socket.setSoTimeout(0);      // Không giới hạn chờ cho read()
socket.setSoTimeout(5_000);  // Read timeout 5 giây
~~~

Tham số là **mili giây**, phải không âm. Khi thời gian chờ dương hết trước khi lời gọi đọc có kết quả, Java ném `java.net.SocketTimeoutException`. Theo hợp đồng của `Socket`, **socket vẫn hợp lệ sau read timeout**; ứng dụng có thể quyết định đọc tiếp, hủy request hoặc đóng kết nối. Timeout **không đồng nghĩa** EOF, và không tự xuất hiện dưới dạng `-1`.

Cần đặt option **trước khi bắt đầu thao tác đọc đang chặn** để nó có hiệu lực rõ ràng.

| Loại timeout | Cấu hình ở đâu? | Bảo vệ thao tác nào? |
|---|---|---|
| **Connect timeout** | `socket.connect(remote, 3_000)` | Thiết lập kết nối TCP |
| **Read timeout** | `socket.setSoTimeout(5_000)` | Một thao tác đọc blocking trên `Socket.getInputStream()` |
| **Accept timeout** | `serverSocket.setSoTimeout(5_000)` | `ServerSocket.accept()` chờ kết nối mới |
| **Deadline toàn bản tin/request** | Tự quản lý thời điểm kết thúc và ngân sách thời gian | Toàn quá trình nhận message, kể cả nhiều lần `read` |

**Cảnh báo:** read timeout không phải deadline của **cả** request. Nếu mỗi lần `read` nhận được một byte trước khi hết 5 giây, một vòng lặp nhận hàng nghìn byte vẫn có thể kéo dài nhiều phút. Giao thức cần **giới hạn kích thước message** và có thể cần deadline tổng quát.

`SO_TIMEOUT` của `Socket` nói trên không phải cách đặt timeout cho mọi `OutputStream.write()`; cũng không tự áp dụng cho `SocketChannel` non-blocking hoặc các thư viện có cơ chế I/O riêng.

## 5. Ví dụ Java 17+ chạy được: thiếu dữ liệu, timeout, dữ liệu tới muộn và EOF

Ví dụ chạy toàn bộ trên loopback (`127.0.0.1` hoặc `::1`), tự tạo server và client trong cùng một JVM; không cần Internet. Server gửi `HELLO`, **cố tình giữ chiều gửi mở** trong khi client thử `read()` với timeout. Sau timeout, client cho phép server gửi thêm `!` rồi gọi `shutdownOutput()`. Client sau đó nhận byte `!` và cuối cùng đọc được `-1`.

Tạo tệp **`TcpReadLifecycleDemo.java`**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;

public class TcpReadLifecycleDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch releaseLastByte = new CountDownLatch(1);
        try (ServerSocket listener =
                new ServerSocket(0, 1, InetAddress.getLoopbackAddress())) {
            Thread sender = new Thread(() -> {
                try (Socket peer = listener.accept()) {
                    peer.getOutputStream().write(
                            "HELLO".getBytes(StandardCharsets.US_ASCII));
                    peer.getOutputStream().flush();
                    releaseLastByte.await();
                    peer.getOutputStream().write('!');
                    peer.getOutputStream().flush();
                    peer.shutdownOutput();
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            }, "demo-sender");
            sender.start();

            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress(
                        InetAddress.getLoopbackAddress(),
                        listener.getLocalPort()), 1000);
                client.setSoTimeout(2000);
                InputStream input = client.getInputStream();
                byte[] five = new byte[5];
                readExactly(input, five);
                System.out.println("message=" +
                        new String(five, StandardCharsets.US_ASCII));
                System.out.println("emptyRead=" + input.read(five, 0, 0));

                client.setSoTimeout(200);
                try {
                    input.read();
                    System.out.println("unexpected=data");
                } catch (SocketTimeoutException expected) {
                    System.out.println("timedOut=true");
                }

                client.setSoTimeout(0);
                releaseLastByte.countDown();
                System.out.println("nextByte=" + (char) input.read());
                System.out.println("eof=" + input.read());
            } finally {
                releaseLastByte.countDown();
                sender.join();
            }
        }
    }

    static void readExactly(InputStream input, byte[] bytes)
            throws IOException {
        int offset = 0;
        while (offset < bytes.length) {
            int count = input.read(bytes, offset, bytes.length - offset);
            if (count == -1) {
                throw new EOFException("Only " + offset +
                        "/" + bytes.length + " bytes");
            }
            offset += count;
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac --release 17 TcpReadLifecycleDemo.java
java TcpReadLifecycleDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
message=HELLO
emptyRead=0
timedOut=true
nextByte=!
eof=-1
~~~

Ý nghĩa của từng kết quả:

1. `message=HELLO`: hàm `readExactly` lặp đến khi đủ năm byte, không phụ thuộc số byte trả về trong từng lần đọc.
2. `emptyRead=0`: lời gọi yêu cầu **0 byte**, cho nên trả 0 ngay; **đây không phải** tín hiệu socket chưa nhận gì.
3. `timedOut=true`: server chưa gửi thêm, vẫn mở chiều gửi; `read()` đợi đủ 200 ms rồi ném `SocketTimeoutException`, **không trả `-1`**.
4. `nextByte=!`: sau timeout, cùng kết nối tiếp tục dùng được; bên gửi cung cấp thêm một byte.
5. `eof=-1`: chỉ sau khi phía gửi gọi `shutdownOutput()` và phía đọc đã tiêu thụ `!`, lần đọc kế tiếp mới quan sát EOF.

`CountDownLatch` làm bài thử **có thứ tự**: server không thể gửi `!` trước khi client bắt được timeout. Cổng TCP được hệ điều hành cấp tự động bằng `ServerSocket(0, ...)`. Việc `setSoTimeout(0)` ngay trước khi nhận `!` cho thấy read có thể chờ mà không có deadline riêng; demo vẫn kết thúc vì server chắc chắn gửi dữ liệu sau khi được giải phóng latch.

## 6. Đọc đúng khi chưa đủ byte

### Cách sai: mặc định một lần đọc là đủ message

~~~java
// Đoạn minh họa lỗi; giả sử input đã được tạo.
byte[] frame = new byte[100];
int n = input.read(frame);
process(frame);  // SAI: n có thể < 100, phần còn lại chưa phải dữ liệu mới!
~~~

Nếu `n == 7` thì 93 byte còn lại trong mảng có thể chỉ là byte mặc định `0` hoặc dữ liệu cũ; nếu `n == -1` thì đã hết luồng, không phải nhận message rỗng. Không dùng `new String(frame)` khi chưa biết chính xác độ dài dữ liệu hợp lệ và charset.

### Cách đúng: lặp đến số byte đã biết

Hàm `readExactly` trong ví dụ hoàn chỉnh xử lý như sau:

~~~java
static void readExactly(InputStream input, byte[] bytes)
        throws IOException {
    int offset = 0;
    while (offset < bytes.length) {
        int count = input.read(bytes, offset, bytes.length - offset);
        if (count == -1) {
            throw new EOFException("Only " + offset +
                    "/" + bytes.length + " bytes");
        }
        offset += count;
    }
}
~~~

Đây là **trích đoạn hàm**, không phải class chạy độc lập. Nó chỉ phù hợp khi **protocol đã biết trước chính xác độ dài** `bytes.length`. Khi số byte chưa đủ, hàm tiếp tục chờ; khi EOF đến sớm, ném `EOFException` để phân biệt **khung bị cắt cụt** với **message đủ**.

Với code thực tế, `DataInputStream.readFully(byte[])` cung cấp sẵn hành vi tương tự. Trên Java 11+, `InputStream.readNBytes(n)` hoặc `readNBytes(buffer, off, len)` cũng có thể giúp lặp đến đủ số byte, nhưng **trả thiếu ở EOF thay vì tự động báo lỗi bằng `EOFException`**; hãy tự kiểm tra độ dài đã nhận.

Nếu `read` bị timeout **sau khi đã tiêu thụ một phần** message, phần byte đó không tự quay lại đầu luồng. Phải giữ trạng thái parser (offset, tổng độ dài, timeout budget) hoặc chủ động đóng kết nối nếu không thể đồng bộ lại; không được bắt exception rồi vô điều kiện parse lại từ byte đầu.

## 7. Muốn biết “đã đủ dữ liệu” thì cần thiết kế khung bản tin

TCP không cung cấp độ dài application message. Giao thức ứng dụng phải chọn **một trong các quy tắc xác định điểm kết thúc** sau:

| Kiểu framing | Cách xác định đủ message | Khi dễ gặp lỗi |
|---|---|---|
| **Độ dài cố định** | Đã nhận đúng N byte | Chỉ gọi `read` một lần rồi dùng luôn mảng |
| **Length-prefixed** | Đọc header chứa độ dài, sau đó nhận đúng N byte body | Header bị cắt cụt, length âm/quá lớn, khác endian |
| **Delimiter** (ví dụ dòng văn bản) | Đọc đến `\\n` hoặc quy tắc kết thúc đã thỏa thuận | Bên gửi không gửi delimiter, không escape delimiter trong payload |
| **EOF-delimited** | Bên gửi đóng **chiều gửi** và bên nhận thấy `-1` | Tái sử dụng kết nối nhưng không gửi EOF nên bên nhận chờ mãi |

### Ví dụ length-prefixed với `DataInputStream`

Protocol định nghĩa: **4 byte độ dài kiểu Java big-endian**, sau đó chính xác N byte payload UTF-8. Phía gửi có thể dùng:

~~~java
// Trích đoạn phía gửi; out là DataOutputStream của socket.
byte[] payload = message.getBytes(StandardCharsets.UTF_8);
out.writeInt(payload.length);
out.write(payload);
out.flush();
~~~

Phía nhận:

~~~java
// Trích đoạn phía nhận; in là DataInputStream của socket.
int length = in.readInt();     // Tự chờ đủ 4 byte; EOF sớm -> EOFException
if (length < 0 || length > 1_048_576) {
    throw new IOException("Invalid frame length: " + length);
}
byte[] payload = new byte[length];
in.readFully(payload);        // Tự chờ đủ N byte; EOF sớm -> EOFException
String message = new String(payload, StandardCharsets.UTF_8);
~~~

Hai đoạn là **thành phần của cùng protocol**, không phải hai chương trình độc lập. Ở đây có giới hạn message **1 MiB** để tránh cấp phát mảng tùy tiện theo số do đối tác gửi. Độ dài phải đo bằng **byte UTF-8** sau mã hóa, không phải `String.length()` của Java.

`length == 0` có thể là **một message rỗng hoàn toàn hợp lệ** nếu protocol cho phép; `length == -1` là **giá trị length không hợp lệ** theo protocol này, **không đồng nghĩa `InputStream.read() == -1`**. `readInt()` có thể đọc số nguyên âm nếu bên gửi cố ý đặt các bit như vậy, trong khi EOF trước khi đủ bốn byte khiến nó ném `EOFException`.

Đối với protocol theo dòng, `BufferedReader.readLine()` trả `String` khi đã đọc được một dòng (hoặc dòng cuối có nội dung khi gặp EOF) và trả **`null`** khi không còn ký tự để đọc lúc EOF. Nếu chưa nhận newline, CR hoặc EOF, lời gọi có thể chờ. **`null` của `readLine()` không phải `-1` của `InputStream.read()`**, dù cùng biểu đạt end-of-stream ở hai cấp API.

## 8. EOF `-1` thực sự đến từ đâu trong TCP?

TCP là kết nối **hai chiều**. Đầu gửi có thể chủ động kết thúc **chiều gửi riêng** bằng:

~~~java
socket.shutdownOutput();
~~~

Theo ngữ nghĩa TCP, các byte đã gửi trước đó được xếp trước tín hiệu kết thúc chiều gửi (FIN) theo thứ tự của luồng. Đầu nhận vẫn phải đọc hết byte đã có; **lệnh `read()` chỉ trả `-1` khi đã chạm đến cuối luồng nhận**. Việc peer gọi `shutdownOutput` không ngăn nó đọc dữ liệu theo chiều ngược lại; đây là một dạng **half-close**.

Dùng `socket.close()` thường đóng tài nguyên và hai chiều socket ở phía gọi; đóng bình thường của peer có thể được quan sát dưới dạng EOF sau khi các byte được tiêu thụ. Nhưng **không phải mọi ngắt kết nối đều dẫn đến `-1`**: TCP reset (RST), lỗi hệ điều hành hoặc mạng có thể gây `SocketException`/`IOException`. Kết nối bị đứt vật lý nhưng hai bên chưa phát hiện cũng có thể khiến một lệnh đọc tiếp tục chờ cho đến khi timeout hoặc lỗi được báo.

Một số API trạng thái **không thay thế được việc đọc**:

- `socket.isConnected()` cho biết socket **từng** kết nối thành công, không phải phép kiểm tra live connection cho từng thời điểm.
- `socket.isClosed()` mô tả trạng thái đóng **local** của đối tượng `Socket`, không chứng minh peer đã hay chưa gửi FIN.
- `socket.getInputStream().available() == 0` chỉ là ước lượng hiện không có byte sẵn có để đọc ngay; **không kết luận EOF** và cũng không chứng minh không còn dữ liệu sẽ tới.
- Không dựa vào `Thread.sleep` để đoán sender đã gửi đủ dữ liệu, hoặc dùng `available()` làm kích thước message.

## 9. Một vài dấu hiệu trông giống nhau nhưng bản chất khác nhau

| Hiện tượng | Cần hiểu là | Xử lý phù hợp |
|---|---|---|
| `read(buffer)` trả `7` khi mong 100 byte | Có **7 byte hợp lệ**, phần còn lại chưa biết | Lưu 7 byte; đọc tiếp 93 byte theo framing |
| `read(buffer)` chờ lâu | Không đủ điều kiện kết thúc lần đọc hiện tại | Kiểm tra sender, framing, timeout, deadline |
| `SocketTimeoutException` | Read timeout đã hết | Xem policy retry/đóng; giữ trạng thái phần message đã nhận |
| `read() == -1` | EOF của input stream | Nếu đang chờ message chưa đủ: báo truncated; nếu đọc đến EOF là protocol: hoàn tất |
| `read() == 0` | Nhận được **byte có giá trị 0x00** | Xử lý byte 0 như dữ liệu bình thường |
| `read(buffer, 0, 0) == 0` | Được yêu cầu đọc 0 byte | Không có ý nghĩa về trạng thái mạng |
| `DataInputStream.readFully` ném `EOFException` | Hết stream trước khi nhận đủ khung | Xử lý protocol error/incomplete frame |
| `BufferedReader.readLine() == null` | EOF trong API đọc dòng | Phân biệt kết thúc hợp lệ với thiếu dòng theo protocol |
| `SocketException: Connection reset` | Một lỗi kết nối, thường do TCP reset | Không diễn dịch thành EOF bình thường |

**Phạm vi:** bảng nói về `Socket`/`InputStream` blocking. Đối với `SocketChannel` ở **non-blocking mode**, `read(ByteBuffer)` có thể trả **`0`** khi tạm thời chưa có byte nào để đọc; `-1` vẫn chỉ EOF. Quy tắc cho channel không được áp ngược vào `Socket.getInputStream().read()` đang blocking.

## 10. Thiết kế tránh chờ vô hạn trong hệ thống thật

Một receiver có thể áp dụng thứ tự thiết kế sau:

1. **Chọn framing rõ ràng**: fixed-size, length-prefixed, delimiter hay EOF-delimited; chỉ dùng EOF-delimited khi sẵn sàng kết thúc chiều gửi sau một bản tin.
2. **Giới hạn kích thước khung** trước khi cấp phát: từ chối length âm, length vượt giới hạn, các trường không hợp lệ hoặc biến thiên độ dài bất thường.
3. **Lặp đọc đến đủ**, dùng số byte thực nhận, cập nhật offset; khi EOF sớm thì báo lỗi khung bị cắt cụt.
4. **Đặt connect timeout và read timeout** theo nhu cầu; nhớ cả timeout phía `accept()` nếu server cần dừng chờ kết nối mới.
5. **Đặt deadline tổng thể nếu cần**: tính thời điểm hết hạn và ngân sách còn lại trước mỗi lần đọc. Không dựa riêng vào timeout làm mới sau từng byte.
6. **Định nghĩa policy đóng kết nối, retry, idempotency**. Sau khi bị timeout giữa một message, tái dùng stream chỉ khi parser biết chính xác phần dữ liệu đã tiêu thụ và có thể tiếp tục an toàn.
7. **Đóng socket bằng try-with-resources** để giải phóng tài nguyên; tránh để thread chờ vô thời hạn do một peer im lặng.

Ví dụ hai bên đợi nhau:

~~~text
Client: write("PING") → readLine() chờ "\n" từ server
Server: readLine() chờ "\n" từ client → chưa tạo response
Kết quả: deadlock logic ở application protocol dù TCP vẫn kết nối.
~~~

Sửa bằng cách thỏa thuận và gửi delimiter, ví dụ client gửi `PING\n`, server đọc đủ dòng rồi gửi `PONG\n` (hoặc dùng framing độ dài thay cho dòng); cả hai nên `flush` đúng lúc nếu có lớp đệm.

Nếu một API báo timeout nhưng bạn cần đọc tiếp, **đừng biến timeout thành một vòng `while(true)` nuốt exception mãi**. Như vậy không còn deadline hiệu lực và có thể làm lộ bug protocol. Với service có request dài, theo dõi timeout, số byte đã nhận và trạng thái khung trong log; tránh in dữ liệu nhạy cảm.

## 11. Tự kiểm tra kiến thức

**Câu 1:** Server gửi 1 KiB rồi giữ kết nối. Client có thể nhận 100 byte ở `read(new byte[1024])` không? **Có.** Đó là một lần đọc hợp lệ. Nếu protocol cần 1 KiB, phải đọc tiếp.

**Câu 2:** Server im lặng nhưng chưa đóng chiều gửi. `read()` có trả `-1` không? **Không vì im lặng đơn thuần.** Nó chờ byte, EOF hoặc exception; nếu `SO_TIMEOUT` dương hết hạn thì ném `SocketTimeoutException`.

**Câu 3:** Có thể coi `available() == 0` là client đã disconnect không? **Không.** Nó không phải probe EOF/live-connection.

**Câu 4:** Sau khi nhận 10/20 byte, peer gửi FIN. Điều gì xảy ra? Vòng lặp đọc tiếp sau 10 byte sẽ gặp **`-1`**. Vì frame cần 20 byte, đó là **khung chưa hoàn chỉnh**, thường được báo bằng `EOFException` hoặc lỗi giao thức.

**Câu 5:** `read(buffer, 0, 0) == 0` có mâu thuẫn với quy tắc “read blocking không trả 0”? **Không.** Lần đọc yêu cầu 0 byte; quy tắc “trả số dương hoặc `-1`” đang nói về **lệnh đọc có độ dài dương** trên input stream blocking.

**Câu 6:** Client đặt `SO_TIMEOUT=2_000` rồi nhận mỗi 1 giây một byte. Liệu cả frame sẽ có deadline hai giây? **Không.** Timeout này áp cho từng lời gọi đọc. Muốn giới hạn tổng thời gian nhận cả frame phải có deadline riêng.

**Câu 7:** Dòng `readLine()` chưa có newline nhưng peer gọi `shutdownOutput()` sau khi gửi `abc`. `readLine()` có thể trả gì? **`"abc"`** cho dòng cuối không kết thúc bằng newline, rồi lần gọi kế tiếp trả `null`. EOF không nhất thiết làm mất dữ liệu còn lại.

## Tài liệu Java chính thức

- [Java 17 – InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): ý nghĩa `read`, `readNBytes`, `readAllBytes` và `available`.
- [Java 17 – Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): `setSoTimeout`, `shutdownInput`, `shutdownOutput`, `connect`.
- [Java 17 – DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readFully` và `EOFException` khi thiếu byte.
- [Java 17 – SocketTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketTimeoutException.html).
- [Java 17 – BufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html): `readLine()` và `null` ở EOF.
- [Java 17 – SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): phân biệt cách đọc blocking và non-blocking.

**Ghi nhớ:** Với `Socket.getInputStream()` blocking, `read(...)` có thể nhận **ít hơn số byte đang mong**, `SO_TIMEOUT=0` cho phép **đợi không giới hạn theo timeout đọc**, còn `-1` biểu thị **EOF thực sự**, không phải “chưa có dữ liệu”. Giải quyết dứt điểm bằng **framing + vòng lặp đọc + xử lý EOF/timeout đúng + giới hạn tài nguyên**.
