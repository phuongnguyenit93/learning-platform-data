# flush ở bộ đệm ứng dụng khác với xác nhận từ ứng dụng phía bên kia

Trong giao tiếp **TCP bằng Java `Socket`**, gọi `OutputStream.flush()` thường là bước cần thiết để đẩy dữ liệu đang nằm trong **bộ đệm của ứng dụng** xuống tầng dưới. Tuy nhiên, **`flush()` trả về không chứng minh ứng dụng nhận đã đọc, xử lý hoặc lưu thành công yêu cầu**. Muốn biết điều đó phải thiết kế **thông điệp xác nhận ở tầng ứng dụng (application-level ACK/response)** và quy định chính xác ACK biểu thị điều gì.

Bài học tập trung vào ba sự kiện dễ bị trộn lẫn: **đẩy dữ liệu khỏi Java buffer**, **TCP bên kia xác nhận byte ở tầng vận chuyển**, và **ứng dụng bên kia trả lời sau khi thực hiện công việc**.

## 1. Bốn mốc hoàn toàn khác nhau trong một lần gửi

Giả sử client gửi yêu cầu `REQ:42` qua một TCP connection. Đường đi có thể được hình dung như sau:

```text
Client Java                              Server Java
+-------------------------+             +----------------------------+
| write(...)              |             |                            |
| BufferedOutputStream    |             |                            |
| [còn byte trong buffer] |             |                            |
+------------+------------+             |                            |
             | flush()                   |                            |
             v                           |                            |
+-------------------------+             |                            |
| Socket OutputStream     |             |                            |
| chuyển byte xuống OS    |             |                            |
+------------+------------+             |                            |
             v                           |                            |
+-------------------------+   TCP       +----------------------------+
| Local TCP send buffer   | ----------> | Remote TCP receive buffer  |
|                         | <---- ACK --| Remote TCP stack           |
+-------------------------+             +-------------+--------------+
                                                     |
                                                     v
                                        +----------------------------+
                                        | readFrame()/read(...)       |
                                        | xác thực / xử lý nghiệp vụ  |
                                        +-------------+--------------+
                                                      |
                                          server gửi "ACK:42"
                                                      |
Client readFrame() <----------------------------------+
(Client nhận application ACK)
```

| Mốc | Điều gì đã xảy ra? | Điều **chưa** được bảo đảm |
| --- | --- | --- |
| 1. `write(...)` vào `BufferedOutputStream` | Byte có thể đang nằm trong bộ đệm Java | Chưa chắc đã được đưa xuống socket |
| 2. `flush()` hoàn tất | Các byte đang chờ trong buffer Java đã được chuyển qua underlying stream theo hợp đồng `flush`, trừ khi có lỗi | Chưa chứng minh byte đến hệ điều hành phía kia, ứng dụng nhận đã `read`, hoặc nghiệp vụ thành công |
| 3. TCP ACK từ phía nhận | TCP stack ở đầu kia xác nhận đã nhận các byte tương ứng theo cơ chế của TCP | Không chứng minh process server đã đọc hay xử lý; Java `Socket` thông thường không cung cấp API "đợi peer TCP ACK cho request này" |
| 4. Application ACK/response | Server chủ động gửi thông điệp trả lời theo **giao thức ứng dụng** | Mức độ xác nhận phụ thuộc vị trí server gửi ACK: sau khi đọc, sau khi validate, sau khi commit, hay chỉ sau khi xếp hàng |

**Từ "ACK" phải kèm ngữ cảnh.** ACK của TCP và `ACK:42` do ứng dụng tự định nghĩa là hai sự kiện khác nhau. Một phía có thể nhận đủ TCP segment và phát ACK ở kernel dù chương trình server chưa gọi `read()` lần nào. Ngược lại, một HTTP 200 hoặc bản tin "OK" là phản hồi **của giao thức ứng dụng**, chỉ có ý nghĩa theo hợp đồng cụ thể của server.

## 2. `flush()` thực sự làm gì trong Java?

### 2.1. Chuỗi stream có nhiều lớp đệm

```java
OutputStream raw = socket.getOutputStream();
BufferedOutputStream buffered = new BufferedOutputStream(raw);
DataOutputStream output = new DataOutputStream(buffered);

output.writeInt(6);
output.write("REQ:42".getBytes(StandardCharsets.UTF_8));
output.flush();
```

*Đây là đoạn mã minh họa nằm trong phương thức đã có biến `socket` và xử lý `IOException`; không phải chương trình độc lập.*

- `DataOutputStream` ghi cấu trúc nhị phân; trong ví dụ này `writeInt(6)` tạo tiền tố độ dài bốn byte.
- `BufferedOutputStream` gom byte trong RAM của JVM. Một lời gọi `write(...)` có thể chỉ sửa buffer của Java, **không** gọi xuống socket ngay.
- `output.flush()` đi qua lớp stream để flush `BufferedOutputStream`, buộc các byte còn đọng được ghi qua `raw`. Ghi xuống socket thành công thường có nghĩa dữ liệu đã được tầng socket cục bộ tiếp nhận để gửi; **không tạo ra bằng chứng phía server đã xử lý**.
- Nếu ghi đủ nhiều để đầy buffer, `BufferedOutputStream` có thể tự đẩy dữ liệu xuống stream nền ngay trong `write()`. Vì vậy không nên khẳng định "không có byte nào lên mạng trước khi flush".
- `OutputStream.flush()` ở lớp cơ sở là **no-op**; ý nghĩa thực tế phụ thuộc implementation và những wrapper đang dùng. Gọi `flush()` trực tiếp trên socket stream không phải một thao tác "ép remote xác nhận".

Tài liệu `java.io.OutputStream` nhấn mạnh rằng flush qua các abstraction do hệ điều hành cung cấp chỉ bảo đảm việc chuyển đến tầng hệ điều hành theo hợp đồng stream, chứ không bảo đảm tác vụ đích đã hoàn tất. Đây là lý do không thể thay application ACK bằng `flush`.

### 2.2. `flush()` có thể ném `IOException`

Nếu stream hỏng, đóng hoặc lỗi I/O được phát hiện, `write`/`flush` có thể thất bại. Nhưng:

- **Lỗi được phát hiện** ⇒ không được ghi nhận request thành công; một phần byte vẫn **có thể** đã đi trước khi lỗi xảy ra.
- **Không có lỗi tại `flush`** ⇒ chỉ xác nhận việc ghi ở phạm vi API cục bộ đã hoàn tất. Server vẫn có thể bị crash, mạng đứt sau đó, hoặc application ACK bị mất.

Vì thế, cả hai trạng thái đều **không xác định trọn vẹn** việc thực hiện nghiệp vụ bên server.

## 3. Ví dụ thực nghiệm Java 17+: flush đã xong nhưng application ACK chưa được gửi

Ví dụ mở một TCP listener trên **loopback** (không cần mạng ngoài), tạo client kết nối vào chính JVM, rồi cho server đọc và xác thực request. Một `CountDownLatch` chủ động **giữ ACK lại** cho tới khi client ghi log rằng `flush()` đã hoàn tất. Như vậy kết quả không phụ thuộc vào `Thread.sleep()` hay tốc độ máy.

Protocol mẫu sử dụng **length-prefix framing**:

- Request: 4 byte `int` độ dài + byte UTF-8 chứa `REQ:42`.
- Response: 4 byte `int` độ dài + byte UTF-8 chứa `ACK:42`.
- Server kiểm tra request trước khi được phép trả lời; client đợi đúng ACK và kiểm tra nội dung.
- Trong ví dụ, `ACK:42` **chỉ chứng minh server handler đã đọc/kiểm tra request và gửi phản hồi**; không có cơ sở dữ liệu hoặc thao tác commit nào.

**Tệp `FlushVsAckDemo.java`:**

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class FlushVsAckDemo {
    static void writeFrame(DataOutputStream out, String text)
            throws IOException {
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        out.writeInt(payload.length);
        out.write(payload);
    }

    static String readFrame(DataInputStream in) throws IOException {
        int length = in.readInt();
        if (length < 0 || length > 4096) {
            throw new IOException("Invalid frame length");
        }
        byte[] payload = new byte[length];
        in.readFully(payload);
        return new String(payload, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch handled = new CountDownLatch(1);
        CountDownLatch permitAck = new CountDownLatch(1);

        try (ServerSocket listener = new ServerSocket(
                0, 50, InetAddress.getLoopbackAddress())) {
            listener.setSoTimeout(5000);
            ExecutorService workers = Executors.newSingleThreadExecutor();
            try {
                Future<?> server = workers.submit(() -> {
                    try (Socket peer = listener.accept()) {
                        peer.setSoTimeout(5000);
                        DataInputStream in = new DataInputStream(
                                new BufferedInputStream(peer.getInputStream()));
                        DataOutputStream out = new DataOutputStream(
                                new BufferedOutputStream(peer.getOutputStream()));

                        String request = readFrame(in);
                        if (!"REQ:42".equals(request)) {
                            throw new IOException("Unexpected request");
                        }
                        handled.countDown();

                        // Cố ý chưa gửi ACK dù server đã read/validate.
                        if (!permitAck.await(5, TimeUnit.SECONDS)) {
                            throw new IOException("ACK gate timeout");
                        }
                        writeFrame(out, "ACK:42");
                        out.flush();
                    } catch (IOException e) {
                        throw new UncheckedIOException(e);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(e);
                    }
                });

                try (Socket client = new Socket(
                        InetAddress.getLoopbackAddress(),
                        listener.getLocalPort())) {
                    client.setSoTimeout(5000);
                    DataOutputStream out = new DataOutputStream(
                            new BufferedOutputStream(client.getOutputStream()));
                    DataInputStream in = new DataInputStream(
                            new BufferedInputStream(client.getInputStream()));

                    writeFrame(out, "REQ:42");
                    out.flush();
                    System.out.println("1. client: flush returned");

                    if (!handled.await(5, TimeUnit.SECONDS)) {
                        throw new TimeoutException("Server did not read");
                    }
                    System.out.println("2. server: request validated");
                    System.out.println("3. client: application ACK not sent yet");

                    // Server bây giờ mới được phép phát phản hồi.
                    permitAck.countDown();
                    String ack = readFrame(in);
                    if (!"ACK:42".equals(ack)) {
                        throw new IOException("Wrong application ACK");
                    }
                    System.out.println("4. client: received ACK:42");
                } finally {
                    // Không để thread server mắc kẹt nếu client gặp lỗi.
                    permitAck.countDown();
                }
                server.get(5, TimeUnit.SECONDS);
            } finally {
                workers.shutdownNow();
            }
        }
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac --release 17 FlushVsAckDemo.java
java FlushVsAckDemo
```

Stdout trong lần chạy thành công:

```text
1. client: flush returned
2. server: request validated
3. client: application ACK not sent yet
4. client: received ACK:42
```

**Đọc đúng kết quả:** dòng 1 chỉ nói local flush hoàn tất; dòng 2 là kết quả quan sát thêm bằng latch dành riêng cho bài demo; dòng 3 chứng minh server vẫn chưa gửi ACK dù cả flush và read/validate đã xong; dòng 4 chỉ xuất hiện sau khi client nhận **khung phản hồi thực sự** qua `readFrame()`. Trong chương trình sản xuất, client không có `handled` latch chia sẻ với process server; nó phải dựa vào **protocol response nhận qua mạng**.

Các giới hạn có chủ ý: chương trình dùng một request, một server thread, loopback và chuỗi ASCII để làm rõ bản chất; latch chỉ tạo một thí nghiệm tất định, không phải cơ chế xác nhận phân tán. `ServerSocket.setSoTimeout(5000)` giới hạn lần `accept()` chờ kết nối; `Socket.setSoTimeout(5000)` giới hạn các thao tác đọc đang chờ, **không** đặt deadline toàn bộ transaction và cũng không tạo application ACK. Dùng `Future.get(...)` để phát hiện lỗi của luồng server thay vì âm thầm bỏ qua.

## 4. TCP là luồng byte, không phải hàng đợi thông điệp

Một lời gọi `output.write(bytes)` ở client không tương ứng 1–1 với một lời gọi `input.read(bytes)` ở server. TCP giữ thứ tự byte trên một connection, còn việc phân đoạn/gom byte do hệ điều hành và mạng quyết định. Ví dụ:

- Client ghi `"HEL"` rồi `"LO"`; server có thể nhận `"HELLO"` trong một lần đọc hoặc thành nhiều lần.
- Client `flush()` một request không tự thêm dấu kết thúc bản tin. Server cần biết **đọc đến đâu là đủ**.
- `DataInputStream.readFully(payload)` đọc cho tới khi đủ độ dài yêu cầu hoặc báo EOF/lỗi. Độ dài phải được kiểm tra trước khi cấp phát mảng để tránh input nguy hiểm.
- Cả hai phía chỉ `read()` mà không flush phần request/response còn trong buffer có thể dẫn tới **deadlock giao thức**.
- Một bên `close()` hoặc `shutdownOutput()` có thể giúp biểu diễn kết thúc luồng trong giao thức EOF-delimited, nhưng không được nhầm với "server đã xử lý"; phải chủ động flush Java buffer **trước** `shutdownOutput()` nếu dữ liệu còn trong wrapper. Với keep-alive/multiplex request, framing rõ ràng thường thích hợp hơn EOF.

Ví dụ trong bài dùng 4 byte độ dài theo `DataOutputStream.writeInt`, sau đó là byte UTF-8; server dùng `readInt`/`readFully` đúng quy ước. `DataInputStream.readUTF()`/`DataOutputStream.writeUTF()` cũng có framing riêng nhưng sử dụng **modified UTF-8** và tiền tố độ dài khác: **không trộn** `writeUTF` với giao thức raw UTF-8 length-prefix khi chưa định nghĩa conversion.

## 5. ACK tầng ứng dụng cần có hợp đồng rõ ràng

Không có một ACK chung phù hợp mọi yêu cầu. Bản tin phản hồi chỉ đáng tin ở mức **server định nghĩa và thực hiện**.

| ACK gửi tại thời điểm | Client có thể kết luận điều gì (nếu tin cậy server/protocol)? | Điều chưa chắc chắn |
| --- | --- | --- |
| Server vừa `read` đủ bytes | Process đã lấy trọn frame khỏi TCP stream | Chưa parse/validate/commit |
| Server đã parse và validate | Dữ liệu hợp cú pháp/chính sách nhập | Chưa thực hiện nghiệp vụ |
| Server đã xếp yêu cầu vào queue | Được nhận vào queue theo hợp đồng | Worker chưa xử lý; queue có thể chưa durable |
| Server đã thực hiện ghi/commit bền vững | Nghiệp vụ đạt tới mốc commit đã thỏa thuận | Các hiệu ứng không đồng bộ về sau có thể chưa xong |
| Server đã hoàn tất toàn bộ nghiệp vụ | Công việc trong phạm vi xác nhận đã thực hiện | Không bao hàm mọi hệ thống ngoài nếu không nằm trong hợp đồng |

Muốn nói "**đã xử lý thành công**" thì server cần gửi ACK **sau** mốc thành công mong muốn. Chẳng hạn, với một lệnh thanh toán hay ghi dữ liệu, ACK sau khi mới đọc socket là quá sớm; nếu đặc tả yêu cầu commit, hãy thực hiện commit trước khi gửi ACK. Nếu đẩy việc vào queue durable, trả `ACCEPTED` thay vì giả vờ đã `COMPLETED`.

Một protocol request/response thực tế nên xác định:

1. **Frame/encoding:** độ dài + UTF-8, newline-delimited, hoặc chuẩn đã chọn. Quy định giới hạn kích thước, phiên bản protocol và cách báo lỗi.
2. **Correlation ID:** ví dụ `requestId=42`; ACK trả cùng ID để không nhầm phản hồi của các request khác trên connection giữ lâu hoặc có concurrency.
3. **Ngữ nghĩa ACK:** `RECEIVED`, `VALIDATED`, `COMMITTED`, `REJECTED`, lỗi tạm thời... chứ không chỉ chữ "OK" mơ hồ.
4. **Thứ tự gửi:** client flush request sau frame hoàn chỉnh; server đọc/kiểm tra/xử lý rồi write và **flush response**.
5. **Timeout/deadline:** đặt giới hạn chờ phản hồi; xử lý đóng socket, EOF, `SocketTimeoutException` và lỗi protocol.
6. **Idempotency:** nếu client gửi lại do timeout, server phải có cách nhận diện request trùng, thường theo ID và khóa nghiệp vụ.

**Không dùng một `boolean sent = true` sau `flush()` để đánh dấu trạng thái `COMPLETED`.** Trạng thái gửi ở local và trạng thái hoàn thành bên server là hai trục quan sát khác nhau.

## 6. Timeout không chứng minh server chưa xử lý

Các tình huống cần phân biệt:

| Hiện tượng ở client | Điều thực sự biết được | Hành động đúng |
| --- | --- | --- |
| `flush()` trả về thành công, chưa có reply | Client đã vượt qua thao tác ghi local | Tiếp tục đợi application ACK theo deadline |
| `flush()` ném `IOException` | Việc ghi local gặp lỗi được phát hiện; có thể đã gửi một phần | Không coi đã thành công; xử lý trạng thái **unknown** nếu tác vụ có side effect |
| TCP ACK (nếu quan sát bằng công cụ mạng) | Kernel nhận xác nhận byte của TCP | Không thay response ứng dụng |
| Server đọc frame rồi bị crash trước khi trả ACK | Client thường chỉ thấy EOF, reset hoặc timeout | Ghi trạng thái uncertain; quyết định retry theo protocol |
| Server commit rồi ACK bị mất | Client timeout **dù nghiệp vụ đã thành công** | Tra cứu trạng thái bằng ID hoặc retry idempotent |
| Client nhận `ACK:42` đúng protocol | Server đã gửi reply theo mốc mà protocol định nghĩa | Chuyển trạng thái tương ứng, kiểm tra ID/trạng thái/kết quả |

Đặc biệt, mất ACK tạo ra tình huống **không thể suy ra "chưa chạy" chỉ từ việc client không thấy ACK**. Nếu client thử lại một yêu cầu có side effect, server có thể thực hiện hai lần. Để đạt hiệu ứng "một lần" trong logic nghiệp vụ, cần idempotency key và lưu kết quả xử lý trùng phù hợp với transaction/commit; riêng TCP, `flush`, hoặc việc retry tự động không tạo exactly-once processing.

**Ví dụ:** client gửi `charge(requestId=42, amount=100)`; server đã trừ tiền và commit, nhưng phản hồi bị mất. Nếu client gửi lại request ID mới, có nguy cơ tính tiền hai lần. Hợp đồng idempotent với cùng ID và cùng dữ liệu sẽ trả lại kết quả đã lưu thay vì chạy nghiệp vụ lần nữa.

Với `Socket.setSoTimeout(...)`, một lần `read()` có thể ném `SocketTimeoutException` khi vượt thời gian chờ đọc. Đó chỉ là timeout của thao tác đọc; muốn deadline **end-to-end**, cần quản lý thời gian cho toàn bộ request, bao gồm connect, queue, send, read, retry và xử lý ở application.

## 7. Các API dễ khiến ta hiểu nhầm flush

### 7.1. `PrintWriter` và `autoFlush`

```java
PrintWriter writer = new PrintWriter(
        socket.getOutputStream(), true, StandardCharsets.UTF_8);

writer.print("PING");      // autoFlush=true không tự flush ở print()
writer.println();          // println() kích hoạt flush khi autoFlush=true

if (writer.checkError()) {
    throw new IOException("Local output error");
}
```

Đoạn mã trên nằm trong một phương thức có `socket` và xử lý `IOException` (Java 17+). Với `PrintWriter`:

- `autoFlush=true` flush khi gọi **`println`, `printf` hoặc `format`**; không có nghĩa mọi `write`/`print` hoặc mọi ký tự `\n` đều tự flush.
- Các phương thức ghi của `PrintWriter` **không ném `IOException` trực tiếp như `DataOutputStream`**; dùng `checkError()` để quan sát error state. `checkError()` tự flush trước khi kiểm tra nếu writer còn mở.
- Dù `println()` đã auto-flush và `checkError()` trả false, vẫn **không chứng minh remote app đã đọc hoặc trả lời**.
- Nếu dùng text line protocol, quy định rõ charset (ví dụ UTF-8), ký tự kết thúc dòng và giới hạn dòng; `BufferedReader.readLine()` có thể chờ mãi nếu phía gửi không phát delimiter hoặc EOF.

### 7.2. `BufferedWriter` / `OutputStreamWriter`

```java
BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(socket.getOutputStream(),
                StandardCharsets.UTF_8));
writer.write("PING");
writer.newLine();
writer.flush();            // đẩy char/byte buffer xuống stream nền
```

*Đoạn minh họa cần biến `socket` và xử lý `IOException` trong hàm bao ngoài.* Khác `PrintWriter` có tùy chọn auto-flush, `BufferedWriter.newLine()` chỉ ghi ký tự kết thúc dòng vào stream và **không mặc định flush ngay**. Việc gọi flush giải quyết **buffer phía gửi**, còn xác nhận remote app vẫn phải đọc reply. Nếu đã bọc `OutputStreamWriter` với bộ mã hóa ký tự, flush còn giúp chuyển character buffer xuống tầng byte stream; nó không cam kết byte đã được remote handler tiêu thụ.

### 7.3. `Socket.getOutputStream()` và `TCP_NODELAY`

Đối với `Socket.getOutputStream()` không có thêm `BufferedOutputStream`, việc gọi `flush()` thường không tạo thêm "gửi ngay" như người học tưởng tượng: socket đã có tầng bộ đệm gửi của hệ điều hành, và `OutputStream.flush()` cơ sở có implementation no-op. `setTcpNoDelay(true)` điều chỉnh **Nagle algorithm** để hạn chế một dạng trì hoãn khi gửi các gói nhỏ; nó **không đổi** định nghĩa `flush()`, không buộc remote process `read()`, và không tạo application ACK.

### 7.4. `close()`, `shutdownOutput()` và EOF

- `close()` của wrapper thông thường flush theo hành vi stream rồi đóng tài nguyên; `Socket.close()` đóng socket. Đóng thành công **không** phải phản hồi ứng dụng.
- Với socket hỗ trợ half-close, `shutdownOutput()` phát tín hiệu kết thúc gửi (FIN theo TCP sau dữ liệu đã đi vào socket); phía nhận có thể thấy EOF sau khi đọc hết dữ liệu. **FIN/EOF không có nghĩa server đã hoàn tất nghiệp vụ.**
- Nếu phía gửi còn giữ dữ liệu trong `BufferedOutputStream`, cần `flush()` wrapper đó trước khi `shutdownOutput()` socket; không giả định `shutdownOutput()` biết cách flush các wrapper Java mà nó không sở hữu.
- Với giao thức còn phải nhận application ACK sau khi gửi xong, half-close có thể phù hợp trong vài protocol, nhưng phải kiểm tra hợp đồng của cả hai phía. Không tự động đóng luôn cả input trước khi đọc phản hồi.

## 8. Thiết kế protocol thực tế và cách đo/kiểm tra

Đối với tác vụ cần tính đúng đắn, có thể tổ chức các mốc:

```text
client: create requestId=42
client: encode frame + write + flush   → local SEND_ATTEMPTED
server: read full frame + validate     → server VALIDATED
server: execute and durable commit     → server COMMITTED
server: write ACK(COMMITTED, 42) + flush
client: read full ACK; verify id/status → client COMMITTED_CONFIRMED
```

Nếu request không có tác động bền vững, có thể trả `PROCESSED` sau xử lý thay vì `COMMITTED`. Nếu server phân tách xử lý bất đồng bộ, trả `ACCEPTED` kèm mã theo dõi và cho client truy vấn trạng thái sau đó. Việc đặt mốc chuẩn giúp các phép đo latency có ý nghĩa:

- `write→flush`: thời gian chờ drain buffer/ghi xuống stream nền ở client.
- `flush→first response byte`: hỗn hợp truyền mạng, queue, server processing và chờ phản hồi.
- `request→ACK`: end-to-end latency theo mốc ACK đã định nghĩa.
- TCP RTT hoặc TCP ACK: đặc trưng tầng vận chuyển, **không** là transaction latency.

Khi debug hiện tượng "client flush rồi mà server chưa xử lý", kiểm tra cả hai phía: server đã `accept` chưa, frame có đầy đủ không, reader đang chờ thêm byte/delimiter không, server có thread/queue bị nghẽn không, server có flush ACK không, đọc response có timeout không. Packet capture có thể chứng minh gói đã tới TCP stack nhưng không trực tiếp chứng minh logic business đã commit; để chứng minh mốc nghiệp vụ cần trace/log kèm correlation ID hoặc trạng thái lưu tại server.

Lưu ý khi dùng TLS: dữ liệu còn đi qua tầng mã hóa/buffer của TLS trước khi xuống TCP; `flush()` ở tầng ứng dụng vẫn **không** trở thành bằng chứng ứng dụng bên kia đã giải mã/xử lý. ACK phải do protocol phía trên TLS xác định.

## 9. Những câu kết luận sai thường gặp

| Khẳng định | Đánh giá và lý do |
| --- | --- |
| "`flush()` không ném lỗi nên phía kia đã nhận message." | **Sai**: có thể mới hoàn tất ghi ở tầng client; TCP ACK/remote app read chưa được chứng minh. |
| "Nhìn thấy TCP ACK nghĩa là server đã xử lý request." | **Sai**: ACK do TCP stack phát, không thay `read`/business logic. |
| "Server đã `read()` một lần là đủ cả message." | **Sai**: TCP là byte stream; phải framing và đọc đủ dữ liệu. |
| "`PrintWriter(autoFlush=true)` flush mọi lần `print`." | **Sai**: auto-flush áp dụng cho `println`/`printf`/`format`. |
| "`Socket.close()` xác nhận server đã commit." | **Sai**: close/FIN/EOF thuộc kết nối, không biểu thị nghiệp vụ. |
| "Timeout chờ ACK nghĩa là chắc chắn server chưa làm gì." | **Sai**: có thể server đã commit nhưng response thất lạc. |
| "Có thể retry bất kỳ request có side effect mà không cần ID." | **Sai**: có nguy cơ xử lý trùng; cần idempotency và quản lý kết quả. |
| "Server gửi `OK` sau khi chỉ enqueue thì mọi tác vụ sau đó đã hoàn tất." | **Sai**: ACK phải nêu rõ `ACCEPTED` hay `COMPLETED` dựa trên mốc thực tế. |

## 10. Bài tập tự kiểm tra

1. Client tạo `BufferedOutputStream(socket.getOutputStream())`, ghi 30 byte rồi chờ server trả phản hồi nhưng không gọi `flush()`. Vì sao hai phía có thể cùng bị kẹt?
2. Server sử dụng `read()` và đã đọc một phần đầu request. Client `flush()` thành công. Ta đã biết được độ dài và nội dung cả request chưa?
3. Khi thấy TCP ACK trong Wireshark, liệu ta có thể kết luận server đã ghi thành công dữ liệu xuống database không?
4. Server commit transaction rồi mất kết nối trước khi gửi ACK. Client nhận timeout. Nên coi trạng thái request là `FAILED` chắc chắn hay `UNKNOWN`? Có thể retry thế nào?
5. Trong ví dụ `FlushVsAckDemo`, muốn ACK nghĩa là "ghi bền vững", cần thay đổi vị trí tạo `ACK:42` ở đâu?
6. `PrintWriter` với `autoFlush=true` được gọi `print("HELLO\n")` nhưng không gọi `println()`. Có thể giả định đã flush hay không?

**Đáp án gợi ý:**

1. Dữ liệu có thể còn nằm trong Java buffer; server chờ frame, còn client chờ ACK. Flush sau khi hoàn thành frame request.
2. Chưa; TCP không giữ ranh giới lời gọi `write`. Đọc theo length-prefix/delimiter và kiểm tra đủ payload.
3. Không; TCP ACK chỉ thể hiện tiến độ tầng TCP.
4. Trạng thái **UNKNOWN**; nếu retry thì giữ nguyên request ID/idempotency key hoặc tra cứu trạng thái trước.
5. Server phải thực hiện và xác nhận commit **trước** khi gửi ACK; thay đổi ngữ nghĩa phản hồi cho đúng và giữ flush response.
6. Không. Auto-flush của `PrintWriter` không kích hoạt chỉ vì có `\n` được ghi qua `print`.

## Tài liệu tham khảo chính thức

- [Java SE 17 — `OutputStream.flush()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): hợp đồng flush và giới hạn của tầng hệ điều hành.
- [Java SE 17 — `BufferedOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html): byte buffer và cách flush xuống underlying stream.
- [Java SE 17 — `PrintWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintWriter.html): phạm vi `autoFlush` và `checkError()`.
- [Java SE 17 — `Socket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): `getInputStream`, `getOutputStream`, `setSoTimeout`, `setTcpNoDelay`, `shutdownOutput`.
- [Java SE 17 — `DataInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readInt`, `readFully` và framing byte.
