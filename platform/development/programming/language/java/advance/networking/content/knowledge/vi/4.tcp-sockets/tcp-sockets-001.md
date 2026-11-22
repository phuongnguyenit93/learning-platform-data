# TCP cung cấp luồng byte có thứ tự; giới hạn của bảo đảm vận chuyển

**Ngữ cảnh:** Java Networking — giao tiếp TCP qua `Socket` và `ServerSocket`. Một ứng dụng có thể gọi `write()` hai lần, phía nhận gọi `read()` ba lần, nhưng vẫn nhận đúng **cùng một dãy byte theo đúng thứ tự**. Đó là đặc tính cốt lõi của TCP; số lần gọi, ranh giới thông điệp và việc nghiệp vụ đã xử lý thành công là những vấn đề khác.

Sau bài này, bạn cần phân biệt được (1) thứ tự và tính tin cậy của **byte stream** với ranh giới **message**, (2) kết quả của `Socket` I/O với việc hệ điều hành hoặc ứng dụng đối diện đã nhận/xử lý dữ liệu, và (3) cơ chế phát hiện lỗi vận chuyển với cơ chế xác nhận nghiệp vụ.

## 1. Mô hình TCP: một kết nối, hai luồng byte có thứ tự

TCP (Transmission Control Protocol) hoạt động trên IP và cung cấp một kết nối logic giữa hai đầu cuối. Trong một kết nối đã thiết lập, dữ liệu ứng dụng được xem là **dãy byte liên tục**, không phải các bản ghi hay gói tin có ý nghĩa nghiệp vụ. Kết nối **full-duplex**: mỗi chiều có luồng byte, thứ tự, trạng thái đóng chiều gửi riêng.

```text
Ứng dụng A                                 Ứng dụng B
OutputStream A ──[byte 0,1,2,3,...]──> InputStream B
 InputStream A <──[byte 0,1,2,3,...]── OutputStream B
       |                                           |
     TCP A ======= IP (có thể mất/đảo gói) ===== TCP B
```

Ứng dụng đọc từ `InputStream` sẽ thấy các byte được phân phối **theo đúng thứ tự chúng được gửi trong cùng chiều của cùng kết nối**, miễn là các byte đó thực sự được giao tới ứng dụng trước khi kết nối lỗi/đóng. TCP nội bộ có thể chia một lần ghi thành nhiều segment, gộp các lần ghi, truyền lại segment mất và nhận segment sai thứ tự, rồi xếp lại trước khi trao byte cho ứng dụng.

Ví dụ gửi `ABCDEF` có thể được ứng dụng chia thành `write("ABC")` và `write("DEF")`. Phía nhận có thể đọc `AB`, `CD`, `EF`; hoặc `A`, `BCDE`, `F`; hoặc tất cả trong một lần `read` đủ lớn. **Dãy byte cuối cùng vẫn là `ABCDEF`.** Mọi cách phân chia ấy đều hợp lệ; đừng gán ranh giới message cho ranh giới `read` hoặc `write`.

Số thứ tự TCP xác định vị trí các byte trong luồng; segment là đơn vị vận chuyển của TCP, còn phương thức `read` chỉ lấy số byte hiện sẵn có theo các quy tắc của stream. Không có ánh xạ một-một giữa **lệnh gọi Java**, **TCP segment** và **message của ứng dụng**.

## 2. TCP đảm bảo những gì, và bằng cơ chế nào?

Trong điều kiện một kết nối hoạt động bình thường, TCP hướng tới việc phân phối luồng byte **có thứ tự, không lặp byte và không bị mất byte âm thầm** cho ứng dụng. Các cơ chế chính:

1. **Sequence number:** định vị byte trong luồng. Nếu segment đến sai thứ tự, bộ nhận có thể giữ byte đến sau để lắp đúng thứ tự trước khi giao cho ứng dụng.
2. **ACK và retransmission:** bên nhận xác nhận tiến độ nhận; bên gửi có thể truyền lại dữ liệu chưa được xác nhận khi phát hiện mất gói. Segment đến lặp không làm ứng dụng thấy byte bị nhân đôi trong cùng luồng.
3. **Checksum:** giúp phát hiện nhiều lỗi truyền dữ liệu ở tầng vận chuyển. Đây không phải bảo vệ mật mã chống sửa đổi có chủ đích và không thay thế TLS hay kiểm tra toàn vẹn ở tầng ứng dụng.
4. **Flow control:** cửa sổ nhận (receive window) phản ánh khả năng bộ đệm đầu nhận; bên gửi không thể cứ gửi vô hạn vượt khả năng nhận.
5. **Congestion control:** điều chỉnh tốc độ gửi theo tình trạng mạng, giảm nguy cơ tắc nghẽn; có thể làm độ trễ và thông lượng biến thiên.

Điểm quan trọng về thuật ngữ **reliable**: TCP cố gắng **khôi phục mất gói trong khi kết nối còn khả năng hoạt động** hoặc cuối cùng báo tình trạng kết nối lỗi. Nó **không cam kết mọi byte sẽ tới đích trong thời gian hữu hạn**, không biến kết nối đứt thành kết nối không đứt, và không đưa ra giao dịch nghiệp vụ “thành công đúng một lần”.

**Ordered delivery** cũng có đánh đổi: nếu byte ở vị trí sớm bị mất, byte đến sau có thể đã nằm trong bộ đệm nhưng chưa thể giao theo thứ tự cho ứng dụng; đây là hiện tượng *head-of-line blocking* trong một luồng TCP.

## 3. Ranh giới bảo đảm: TCP không phải giao thức message hay xác nhận nghiệp vụ

| Điều thường bị hiểu nhầm | Điều TCP/Java thật sự nói được |
| --- | --- |
| `write(bytes)` trả về mà không lỗi | Java đã hoàn thành lời gọi ghi vào stream theo giao diện; **không chứng minh** ứng dụng đối diện đã xử lý hay dữ liệu đã được lưu bền vững |
| Một ACK của TCP đã được gửi về | Bên nhận TCP xác nhận byte thuộc luồng theo giao thức; **không phải** ACK của logic ứng dụng |
| Một lần `write` là một message | TCP không giữ ranh giới lần ghi; phía đọc có thể tách/gộp tùy thời điểm và buffer |
| `read(buffer)` lấp đầy cả buffer | Thường chỉ trả về **một số byte dương ≤ kích thước cần đọc**; phải dùng vòng lặp khi cần nhiều byte |
| Kết nối TCP đang `isConnected() == true` | Từng kết nối thành công; không chứng minh peer hiện sống hay mọi dữ liệu tương lai sẽ được chuyển |
| TCP “đảm bảo có thứ tự” | Chỉ **trong một chiều của một kết nối cụ thể**; không sắp thứ tự qua kết nối khác hoặc qua các request độc lập |
| TCP bảo đảm “exactly once” | Loại bỏ byte trùng trong stream đang vận hành; **không** loại bỏ lệnh nghiệp vụ trùng khi ứng dụng gửi lại sau mất kết nối |
| TCP tự mã hóa/xác thực | TCP không làm việc này; ứng dụng cần TLS và cơ chế xác thực phù hợp |

Ba tầng xác nhận phải tách rõ:

```text
Client gọi write()
  → dữ liệu đi vào đường gửi/buffer của client
    → TCP peer nhận và ACK dữ liệu
      → ứng dụng peer đọc/giải mã request
        → ứng dụng peer thực hiện, commit kết quả
          → peer gửi application ACK/response
```

Các mốc bên phải không được suy ra từ mốc bên trái. Ngay cả khi client đã nhận response, vẫn cần định nghĩa cụ thể **response được gửi trước hay sau commit** nếu muốn dùng nó để xác nhận thành công bền vững.

Khi kết nối lỗi vào thời điểm mơ hồ, dữ liệu có thể đã tới server và được commit dù client chưa thấy response. Gửi lại nguyên lệnh trên kết nối mới có nguy cơ **thực hiện hai lần** nếu giao thức không hỗ trợ khóa idempotency/deduplication.

## 4. Đọc/ghi qua `java.net.Socket`: nhìn đúng ngữ nghĩa API

Một `ServerSocket` lắng nghe và `accept()` trả về `Socket` đã kết nối. Mỗi `Socket` có một `InputStream` để đọc luồng byte đến và một `OutputStream` để ghi luồng byte đi.

Đoạn minh họa (các biến `socket` và `payload` đã được khai báo ở ngữ cảnh chương trình, không phải ví dụ độc lập):

```java
socket.getOutputStream().write(payload); // Không tạo ranh giới message.
byte[] buffer = new byte[4096];
int n = socket.getInputStream().read(buffer);

// n là số byte thực sự đọc được; -1 biểu thị EOF.
// Nếu n > 0, chỉ buffer[0..n) chứa dữ liệu vừa đọc.
```

### `InputStream.read` có thể trả về ít hơn yêu cầu

Khi đọc tối đa 4096 byte, `read(buffer)` **không hứa** trả về 4096 byte. Với một stream blocking thông thường, nó có thể trả về một số byte dương nhỏ hơn dù peer còn gửi tiếp; `-1` báo EOF khi đã hết dữ liệu và phía gửi đóng luồng một cách có trật tự. Gọi `read(buffer, off, 0)` được phép trả về `0` do yêu cầu đọc độ dài bằng không. Trong vòng lặp thông thường dùng buffer không rỗng, nên xử lý riêng `-1` và số byte đọc được.

Không dùng `InputStream.available()` để hỏi **độ dài toàn bộ message**: nó chỉ là ước lượng số byte có thể đọc ngay mà không blocking theo hợp đồng API, không phải tổng byte của request hay dữ liệu sắp đến.

### `OutputStream.write` không có nghĩa “peer đã nhận”

Một lần `write` có thể sao chép byte vào hệ thống đệm gửi và trả về trước khi peer nhận. Ngược lại, nếu buffer gửi đầy hoặc mạng chậm, lời gọi ghi có thể block. `flush()` trên `BufferedOutputStream` đẩy các byte đang nằm trong bộ đệm Java xuống stream nền; nó **không tạo record TCP**, không mặc nhiên đợi peer ứng dụng đọc và không tương đương một application ACK. Trên raw socket output stream, không nên suy ra `flush()` có ý nghĩa “đã xác nhận ở đầu kia”.

Với chuỗi văn bản, luôn xác định rõ charset (thường là UTF-8) **sau khi đã ghép đủ byte của một message**: một ký tự UTF-8 có thể bị chia giữa hai lần đọc. Đừng giải mã từng chunk byte thành `String` rồi giả định không mất ký tự ở điểm cắt.

## 5. Ví dụ Java 17+: hai lần ghi, nhưng không đọc theo ranh giới lần ghi

Ví dụ dùng loopback và cổng hệ điều hành tự cấp (port `0`), chạy trong cùng một JVM. Nó chủ động dùng buffer 2 byte để thấy vòng lặp cần ghép nhiều phần; **số lần `read` thực tế không phải kết quả ổn định để kiểm thử**.

Lưu tệp **`TcpStreamChunks.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class TcpStreamChunks {
    public static void main(String[] args) throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 1, InetAddress.getLoopbackAddress());
             Socket writer = new Socket(
                InetAddress.getLoopbackAddress(), listener.getLocalPort());
             Socket reader = listener.accept()) {

            OutputStream out = writer.getOutputStream();
            out.write("ABC".getBytes(StandardCharsets.UTF_8));
            out.write("DEF".getBytes(StandardCharsets.UTF_8));
            writer.shutdownOutput();

            InputStream in = reader.getInputStream();
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            byte[] buffer = new byte[2];
            int n;
            while ((n = in.read(buffer)) != -1) {
                bytes.write(buffer, 0, n);
            }

            System.out.println(new String(
                    bytes.toByteArray(), StandardCharsets.UTF_8));
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```sh
javac -encoding UTF-8 TcpStreamChunks.java
java TcpStreamChunks
```

Stdout xác định:

```text
ABCDEF
```

Tại phía gửi có hai lời gọi ghi (`ABC`, `DEF`). Phía nhận dùng buffer 2 byte nên có thể cần nhiều lượt đọc, nhưng việc ghép theo thứ tự cho ra `ABCDEF`. Code không kiểm tra “lần đọc thứ nhất chính xác bao nhiêu byte”, vì đó là chi tiết timing/buffering, không phải hợp đồng TCP.

`writer.shutdownOutput()` báo kết thúc **chiều gửi của client**: sau khi đã đọc các byte trước FIN, bên nhận mới thấy `read() == -1` và thoát vòng lặp. Chương trình minh họa này ghép đến EOF trong phạm vi một kết nối gửi một nội dung rồi half-close; **không thể sao chép nguyên kỹ thuật “đọc tới EOF” vào giao thức giữ kết nối mở để gửi nhiều message liên tiếp**. `ByteArrayOutputStream` cũng tăng theo dữ liệu, nên không thích hợp nhận dữ liệu không giới hạn từ peer không tin cậy.

## 6. Làm sao biết một message kết thúc? Cần framing ở tầng ứng dụng

Vì TCP không mang ranh giới message, bạn phải **định nghĩa framing** trước khi giải mã dữ liệu hoặc chuyển sang xử lý request tiếp theo. Ba lựa chọn phổ biến:

| Framing | Cách biết kết thúc | Điều kiện/rủi ro cần xử lý |
| --- | --- | --- |
| **Length-prefix** | Header mang độ dài payload, theo sau đúng số byte đó | Giới hạn kích thước, endian, length âm/overflow, EOF nửa chừng |
| **Delimiter** (`\n`, CRLF, ký tự phân tách) | Đọc đến dấu kết thúc | Escape delimiter trong payload, giới hạn dòng, charset |
| **Đến EOF** | Đọc tới khi peer đóng chiều gửi | Chỉ dùng khi protocol quy định một body đến lúc đóng; không phù hợp trao đổi nhiều message cùng chiều trên một kết nối còn mở |

Ví dụ frame tối giản dùng **4 byte số nguyên big-endian** và payload UTF-8:

```text
+------------------------+-------------------------------------+
| 4 byte length = N      | N byte payload (UTF-8)             |
+------------------------+-------------------------------------+
| readInt()              | readFully(byte[N])                 |
+------------------------+-------------------------------------+
```

Nếu gửi hai frame liên tiếp, bộ nhận lặp lại **đọc header → kiểm tra độ dài → đọc đủ N byte → xử lý frame**. Trong Java, `DataOutputStream.writeInt` và `DataInputStream.readInt` thống nhất cách biểu diễn số nguyên; `DataInputStream.readFully` cố đọc đủ byte hoặc ném `EOFException` khi stream kết thúc quá sớm. Tuyệt đối không cấp phát mảng từ độ dài do peer truyền mà chưa kiểm tra giới hạn hợp lý.

Độ dài phải tính theo **byte đã mã hóa**, ví dụ `payload.getBytes(StandardCharsets.UTF_8).length`, không phải số ký tự trong `String.length()`. Một ký tự tiếng Việt thường chiếm nhiều hơn một byte trong UTF-8.

## 7. Ví dụ Java 17+ hoàn chỉnh: frame, EOF và half-close hai chiều

Ví dụ thứ hai thể hiện: header độ dài 4 byte; payload được ghi qua **hai** lời gọi `write`; `readFully` đọc đúng số byte bất kể chúng được vận chuyển theo segment/chunk nào; client half-close chiều gửi nhưng **vẫn đọc được response** từ server.

Lưu tệp **`TcpFrameAndHalfClose.java`**:

```java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class TcpFrameAndHalfClose {
    public static void main(String[] args) throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 1, InetAddress.getLoopbackAddress());
             Socket client = new Socket(
                InetAddress.getLoopbackAddress(), listener.getLocalPort());
             Socket server = listener.accept()) {

            client.setSoTimeout(10_000);
            server.setSoTimeout(10_000);

            byte[] payload = "Tiếng Việt TCP".getBytes(StandardCharsets.UTF_8);
            DataOutputStream sender = new DataOutputStream(
                    client.getOutputStream());

            sender.writeInt(payload.length);
            sender.write(payload, 0, 2);
            sender.write(payload, 2, payload.length - 2);
            sender.flush();
            client.shutdownOutput();

            DataInputStream receiver = new DataInputStream(
                    server.getInputStream());

            int length = receiver.readInt();
            if (length < 0 || length > 1024) {
                throw new IOException("Invalid frame length: " + length);
            }

            byte[] frame = new byte[length];
            receiver.readFully(frame);
            System.out.println("Frame: " +
                    new String(frame, StandardCharsets.UTF_8));
            System.out.println("Client EOF: " + (receiver.read() == -1));

            server.getOutputStream().write(new byte[] {'O', 'K'});
            server.shutdownOutput();

            byte[] reply = new byte[2];
            new DataInputStream(client.getInputStream()).readFully(reply);
            System.out.println("Reply: " +
                    new String(reply, StandardCharsets.UTF_8));
        }
    }
}
```

Chạy:

```sh
javac -encoding UTF-8 TcpFrameAndHalfClose.java
java TcpFrameAndHalfClose
```

Stdout xác định trên một lần chạy thành công:

```text
Frame: Tiếng Việt TCP
Client EOF: true
Reply: OK
```

Trình tự:

1. Client gửi `writeInt(payload.length)` và payload UTF-8; hai lần `write` payload không tạo hai message.
2. Client gọi `shutdownOutput()`. Server đọc được trọn frame bằng `readInt` + `readFully`; lệnh `read()` sau frame trả `-1` khi nhận hết dữ liệu trước FIN.
3. Server vẫn ghi lại `OK` theo chiều ngược lại, rồi `shutdownOutput()`. Client vẫn đọc được hai byte response vì TCP là full-duplex.

`setSoTimeout(10_000)` đặt giới hạn chờ cho **lần đọc blocking trên socket**; nó có thể ném `SocketTimeoutException` nếu không có dữ liệu kịp thời, nhưng không phải bộ đếm thời gian tuyệt đối cho toàn bộ một message dài được gửi nhỏ giọt. Một hệ thống thực cần thêm giới hạn tổng thời gian, số byte, số kết nối và hành vi hủy/đóng phù hợp.

Trong ví dụ, response cố định chính xác hai byte nên client dùng `readFully(reply)`. Với response thực tế, bạn cũng phải tự định nghĩa framing, giới hạn độ dài và trạng thái lỗi. `shutdownOutput` là cơ chế half-close, **không phải application ACK** và không chứng nhận dữ liệu được commit.

## 8. EOF, FIN, RST và khi nào một kết nối coi là kết thúc?

- **FIN / orderly shutdown:** khi peer đóng chiều gửi có trật tự và toàn bộ byte trước FIN đã được đọc, stream trả EOF (`-1`). Ở chiều còn lại, kết nối có thể vẫn tiếp tục gửi dữ liệu.
- **`Socket.shutdownOutput()`:** báo rằng ứng dụng không gửi thêm byte theo chiều này; mọi byte đã xếp trước tín hiệu kết thúc vẫn nằm trước FIN theo thứ tự luồng. Việc gửi tiếp theo sau khi shutdown output không còn hợp lệ.
- **`Socket.close()`:** giải phóng socket và cả hai stream phía Java. Hành vi ở tầng TCP phụ thuộc trạng thái kết nối/buffer/tùy chọn; **không suy ra mọi byte đang chờ đã được peer ứng dụng xử lý**.
- **RST / abort:** kết nối có thể bị reset và phía đọc/ghi gặp `SocketException`/`IOException` thay vì EOF êm. Tương tự, ứng dụng bị crash, tiến trình bị kill hoặc đứt mạng có thể khiến thông điệp chỉ gửi/nhận được một phần.
- **`Socket.isConnected()`:** chỉ cho biết socket đã từng được kết nối thành công; không phải kiểm tra health hiện tại. `isClosed()` nói về trạng thái đóng phía object local, không là bằng chứng “peer vừa đọc xong”.
- **Half-open hoặc kết nối mất liên lạc:** có thể cần timeout, keepalive hoặc heartbeat tầng ứng dụng để phát hiện. TCP keepalive không là bộ định thời nghiệp vụ chính xác và thường không có phản hồi nhanh theo mặc định.

Khi đọc frame mà mới nhận được header hoặc vài byte payload rồi EOF, giao thức phải coi frame đó là **chưa hoàn chỉnh**. Đừng đưa payload dở dang vào nghiệp vụ như một message hợp lệ.

## 9. Cách xử lý lỗi và độ trễ trong Java socket blocking

| Vấn đề | Cách ứng dụng nên làm |
| --- | --- |
| Kết nối quá lâu | Dùng `Socket.connect(endpoint, timeoutMillis)` cho connect timeout và xử lý `IOException` |
| `read` có thể chờ vô hạn | Dùng `setSoTimeout` cho blocking read; thêm deadline end-to-end ở tầng giao thức nếu cần |
| Header length không tin cậy | Kiểm tra `0 <= length <= MAX_FRAME_BYTES` (nếu cho phép body rỗng), không cấp phát vô hạn |
| `EOFException` giữa frame | Loại frame thiếu, đóng phiên xử lý lỗi và ghi rõ điểm hỏng |
| Ghi khi peer/mạng lỗi | Bắt `IOException`; không mặc định “chưa xử lý ở server” |
| Nhiều peer gửi nhanh hơn khả năng xử lý | Hạn chế kết nối/buffer/queue, áp dụng backpressure, tránh vô hạn thread hoặc mảng |
| Reconnect sau failure | Dùng phiên TCP mới; tự thiết kế replay/resume, ID message và xử lý duplicate nếu nghiệp vụ đòi hỏi |

Một `SocketTimeoutException` khi đọc báo rằng **lệnh đọc đã hết thời gian chờ dữ liệu**; nó không có nghĩa server chắc chắn chưa chạy request. Tương tự, thao tác ghi thành công không phải bảo đảm peer đã đọc. Nếu ứng dụng retry ngay mà không có idempotency, một thao tác như trừ tiền hoặc tạo đơn hàng có thể thực hiện hai lần.

Không dùng `Thread.sleep` làm cơ chế “đợi đủ toàn bộ message”: dữ liệu mạng có độ trễ không xác định và việc ngủ không xác định được ranh giới nội dung. Dùng framing và API đọc đủ byte.

## 10. Muốn biết server đã thực hiện nghiệp vụ thì cần ACK của ứng dụng

Ví dụ giao thức cho thao tác không được lặp:

```text
Client                               Server
  | -- COMMAND{id=123, body=...} -->  |
  |                                   | kiểm tra idempotency key
  |                                   | thực hiện và commit bền vững
  | <-- RESULT{id=123, committed} --  |
```

**Quy tắc thiết kế:**

1. Gán **request ID/idempotency key** ổn định cho cùng một ý định nghiệp vụ. Retry dùng lại key cũ, không tạo một ý định mới.
2. Server kiểm tra key, lưu kết quả và thực hiện thay đổi trong cơ chế nhất quán phù hợp (ví dụ transaction với unique constraint) để các retry đồng thời không tạo nhiều hiệu ứng.
3. Chỉ gửi **application response/ACK sau mốc cam kết** mà giao thức định nghĩa; mô tả rõ response có nghĩa “nhận yêu cầu”, “đã xếp hàng” hay “đã commit”.
4. Khi mất kết nối sau commit nhưng trước khi client nhận response, client có thể retry cùng key; server trả lại kết quả cũ hoặc trạng thái đã xử lý.
5. Xác định phạm vi và thời gian lưu key, xử lý key bị tái sử dụng với payload khác, và tránh xóa lịch sử dedup quá sớm.

Như vậy, **TCP bảo toàn thứ tự byte trong kết nối**, còn khả năng chịu retry và chống xử lý trùng là **hợp đồng tầng ứng dụng phối hợp với lưu trữ**. Không một cờ trên `Socket` tự biến write/ACK của TCP thành giao dịch exactly-once.

## 11. Hiệu năng: buffering, backpressure và head-of-line blocking

TCP tối ưu hóa chuyển **byte**, không ưu tiên việc giữ nguyên số lệnh `write`. Những thao tác rất nhỏ có thể bị ảnh hưởng bởi Nagle’s algorithm, delayed ACK, kernel buffering và lịch trình mạng; những thao tác rất lớn có thể bị phân nhỏ. `Socket.setTcpNoDelay(true)` điều chỉnh hành vi Nagle để cải thiện độ trễ trong một số mô hình ghi nhỏ; nó **không** biến TCP thành giao thức message và có thể làm tăng số segment/overhead.

Khi peer đọc chậm, cửa sổ nhận thu hẹp và bên gửi có thể bị nghẽn; khi mạng tắc, congestion control giảm tốc độ. Khi byte sớm chưa đến, TCP cần lấp chỗ trống thứ tự trước khi giao các byte sau; một lệnh nghiệp vụ “nhỏ, khẩn” gửi trên cùng luồng không tự vượt qua dữ liệu đi trước.

Vì vậy, trên đường xử lý Java:

- Xác định **framing** và **số byte tối đa mỗi message**, tránh đọc một stream mở mãi bằng `readAllBytes()` không giới hạn.
- Đo **latency p95/p99**, số kết nối, số byte chờ, timeout, lần retry và áp lực buffer; không dùng số lượng `write`/`read` như proxy cho số message.
- Nếu dùng `BufferedOutputStream`, flush tại **thời điểm frame hoàn chỉnh** cần phát ra theo giao thức; không kỳ vọng flush là TCP ACK.
- Đặt giới hạn tổng thời gian và lưu lượng; ngừng nhận/thực thi khi xử lý phía sau quá tải thay vì tạo queue không giới hạn.
- Với nhiều loại request khác nhau trên một kết nối, cân nhắc thứ tự xử lý và giao thức multiplexing ở tầng cao hơn; không giả định TCP tự cho vượt luồng bị nghẽn.

## 12. Các lỗi thường gặp và cách sửa

**Lỗi 1: “Một `write` ứng với một `read`.”** Nếu dùng `read(buffer)` một lần rồi parse JSON như đã đủ request, có thể nhận nửa JSON hoặc nhiều JSON nối nhau. **Sửa:** length-prefix, delimiter có escape/limit, hoặc giao thức có ranh giới rõ.

**Lỗi 2: “`read` chưa lấp đầy buffer nên peer gửi thiếu.”** Trả về ít byte hơn giới hạn buffer là hợp lệ, không chứng minh dữ liệu bị mất. **Sửa:** lặp đến đúng số byte framing yêu cầu; kiểm tra EOF/timeout.

**Lỗi 3: “`available() == 0` nghĩa là hết message.”** 0 có thể chỉ nghĩa là lúc đó chưa có byte đọc ngay. **Sửa:** dùng giao thức framing, không suy đoán bằng thời điểm có dữ liệu.

**Lỗi 4: “`flush` là dấu kết thúc message.”** Flush chỉ liên quan đến các tầng buffer, không chèn dấu phân cách. **Sửa:** ghi header/delimiter thật và flush nếu có wrapper buffering.

**Lỗi 5: “TCP ACK nghĩa là server đã lưu giao dịch.”** ACK ở TCP là tầng vận chuyển. **Sửa:** response ứng dụng sau commit và idempotency khi retry.

**Lỗi 6: “Đã gửi lần trước nên reconnect sẽ nhận tiếp tự động.”** Kết nối TCP mới có luồng byte và trạng thái mới; các byte chưa xác nhận hoặc trạng thái xử lý nghiệp vụ trước đó không được TCP tự đồng bộ giữa hai phiên. **Sửa:** thiết kế resume/replay và dedup riêng.

**Lỗi 7: “TCP bảo đảm tuyệt đối dữ liệu luôn đến.”** Mạng, máy, tiến trình, TCP stack và timeout có thể hỏng; ứng dụng có thể chỉ biết kết quả *không xác định*. **Sửa:** xử lý EOF, reset, timeout, lỗi, và định nghĩa rõ cách xác nhận/retry.

**Lỗi 8: “TCP bảo vệ nội dung khỏi bị đọc/sửa.”** TCP checksum không mã hóa và không xác thực người gửi. **Sửa:** dùng TLS phù hợp cùng xác minh danh tính/ủy quyền ở tầng ứng dụng.

## 13. Tự kiểm tra mức hiểu

1. Client gọi `write("A")` rồi `write("B")`; server gọi `read(buffer)` một lần và nhận byte `AB`. Có lỗi không? **Không:** TCP giữ thứ tự, không giữ ranh giới write.
2. Server nhận length-prefix bằng `readInt()`, sau đó `read(payload)` một lần trả ít hơn độ dài khai báo. Có phải mất dữ liệu? **Chưa thể kết luận:** dùng `readFully`/vòng lặp và xử lý EOF hoặc timeout.
3. Client ghi thành công rồi mất kết nối trước response; có an toàn khi gửi lại lệnh “trừ 100” không? **Chưa:** lệnh cũ có thể đã commit. Cần idempotency key và kết quả nghiệp vụ có thể truy vấn/nhận lại.
4. Server gọi `shutdownOutput` thì client có thể tiếp tục gửi vào server không? **Có thể**, vì server chỉ đóng chiều **gửi** của nó; phía nhận của server vẫn có thể hoạt động cho đến khi được đóng.
5. Đã có TCP checksum thì bỏ TLS được không? **Không:** checksum không cung cấp bảo mật, bí mật, xác thực hoặc toàn vẹn mật mã.

## 14. Kết luận thực hành

Hãy nhớ hai mệnh đề riêng:

- **TCP:** byte được chuyển đến ứng dụng nhận theo **đúng thứ tự trong mỗi chiều của một kết nối**, với cơ chế truyền lại, cửa sổ nhận và kiểm soát tắc nghẽn; khi đường truyền hay đầu cuối lỗi, kết nối có thể dừng trước khi truyền xong.
- **Ứng dụng:** phải tự xác định **ranh giới message**, kiểm tra độ dài/định dạng, quản lý timeout, phản hồi nghiệp vụ và retry/idempotency. `write()`, FIN hoặc ACK của TCP không thay thế response sau commit.

Tham khảo API chuẩn: [Java SE 17 Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html), [ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html), [InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html), [DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html), và [RFC 9293 — Transmission Control Protocol](https://www.rfc-editor.org/rfc/rfc9293).