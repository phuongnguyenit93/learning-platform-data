# Nhận diện tình huống hai phía cùng chờ đọc và quy định thứ tự trao đổi

Trong một kết nối TCP, client và server **đều có quyền đọc và ghi**; TCP không quy định bên nào phải nói trước. Vì vậy, giao thức ứng dụng phải tự xác định **ai gửi trước, gửi bao nhiêu dữ liệu, khi nào một thông điệp hoàn chỉnh và bên nào được chờ phản hồi**.

Lỗi điển hình: client gọi `readLine()` để đợi server, trong khi server cũng gọi `readLine()` để đợi client. Không bên nào gửi dữ liệu đầu tiên. Cả hai có thể chờ vô hạn dù TCP đã kết nối thành công, cổng đúng và đường mạng hoạt động bình thường.

Đây là **bế tắc do thứ tự trao đổi của giao thức** (protocol-level circular wait). Cần phân biệt nó với TCP mất gói, server chậm hoặc lỗi kết nối: việc tăng timeout hay bật `TCP_NODELAY` không giải quyết được một giao thức mà cả hai phía đều được lập trình để đợi đầu vào trước.

## 1. Mô hình: TCP là hai luồng byte độc lập, không có lượt nói tự động

Đối với một `java.net.Socket`, ứng dụng nhận `InputStream` và `OutputStream`. TCP bảo toàn thứ tự **byte** trên từng chiều của kết nối, nhưng **không bảo toàn ranh giới lời gọi `write()` thành thông điệp**. Thư viện không tự thêm "request" hay "response".

- `socket.getInputStream().read()` có thể đợi cho tới khi có byte, EOF, timeout đã cấu hình hoặc lỗi I/O. Nó **không khiến đối tác tự gửi dữ liệu**.
- `BufferedReader.readLine()` chờ ký tự kết thúc dòng (`\n`, `\r` hoặc `\r\n`) hoặc EOF; có byte nhưng chưa có dấu kết thúc dòng thì vẫn có thể đang chờ.
- `DataInputStream.readInt()` cần **đủ bốn byte**. `readFully(byte[])` cần đủ số byte được yêu cầu; nếu chưa đủ, phương thức có thể đợi thêm.
- `OutputStream.write(...)` ghi byte vào đường gửi; với `BufferedOutputStream`/`BufferedWriter`, byte có thể còn nằm trong buffer Java tới khi `flush()` hoặc buffer đầy.
- `socket.setSoTimeout(milliseconds)` đặt giới hạn chờ cho thao tác đọc blocking của socket. Giá trị `0` nghĩa là không giới hạn thời gian; timeout tạo ra ngoại lệ, **không tự hoàn tất thông điệp hoặc phá được thiết kế giao thức sai**.

Hình sau minh họa khi hai phía đọc trước khi viết:

```text
Client                                         Server
  |                                             |
  | TCP connect ------------------------------>  | accept()
  |                                             |
  | readLine()  (đợi server gửi trước)           |
  |                                             | readLine()
  |                                             | (đợi client gửi trước)
  |                  KHÔNG BÊN NÀO GHI          |
  |                                             |
  | <------------ cả hai cùng chờ -------------->|
  |                                             |
  | nếu SO_TIMEOUT được đặt:                     |
  | SocketTimeoutException                      | SocketTimeoutException
  v                                             v
```

**Điểm mấu chốt:** `connect()`/`accept()` thành công chỉ xác lập kết nối; chúng không mặc nhiên gửi thông điệp chào, mã lệnh hay nội dung nghiệp vụ. Không nên nhầm "đã kết nối" với "đã nhận đủ request".

## 2. Cách nhận diện các dạng chờ vòng tròn

Không phải mọi trường hợp chờ đọc đều do "hai phía đều gọi `read()` trước"; nguyên nhân có thể là **điều kiện để một bên gửi không bao giờ được bên kia đáp ứng**.

| Tình huống | Client đang chờ | Server đang chờ | Nguyên nhân cần kiểm tra |
| --- | --- | --- | --- |
| **Hai phía đều đọc trước** | `readLine()` đợi lời chào | `readLine()` đợi request | Không có thông điệp mở đầu |
| **Client ghi nhưng chưa flush** | Đợi phản hồi | Đợi request từ socket | Byte còn ở `BufferedWriter`/`BufferedOutputStream` |
| **Thiếu delimiter** | Đợi ACK | `readLine()` đợi newline hoặc EOF | Client viết `"PING"` nhưng không gửi `\n` |
| **Độ dài frame sai** | Đợi ACK | `readFully()` đợi thêm byte | Prefix báo 100 byte nhưng client gửi 20 |
| **Server chờ EOF** | Đợi response, giữ output mở | Đọc đến EOF mới bắt đầu xử lý | Hai bên không thống nhất kết thúc request |
| **Cả hai ghi khối lớn trước khi đọc** | `write()` có thể bị block vì send buffer đầy | `write()` cũng có thể bị block | Không bên nào drain luồng nhận; backpressure hai chiều |
| **Handshake lệch lượt** | Đợi `READY` trước khi gửi AUTH | Đợi AUTH trước khi gửi `READY` | Hai bản đặc tả/phiên bản protocol khác nhau |
| **Không đọc/flush response** | Đợi dòng trả lời | Đã `write("OK")` nhưng giữ trong buffer | Thiếu `flush()` hoặc dấu kết thúc |

Vì TCP là luồng byte, một lần `write()` ở client **có thể được server thấy qua nhiều lần `read()`**, hoặc nhiều lần write có thể gom lại trong một lần read. Cho nên cần framing và thứ tự trao đổi rõ ràng, không dựa vào giả định "mỗi write tương ứng một read".

**Phân biệt với hỏng mạng:** nếu packet capture/trace cho thấy request đã tới nhưng server vẫn chờ, hãy kiểm tra parser đang đợi delimiter/đủ length hay chờ một event nghiệp vụ khác. Nếu không có byte nào xuất hiện ở socket phía gửi, kiểm tra bước write/flush và đường đi trước khi kết luận do TCP. Một thread dump cho thấy cả hai thread đọc blocking là dấu hiệu mạnh của lỗi choreography nhưng phải đối chiếu log trạng thái protocol.

## 3. Phác họa quan hệ chờ để tìm điểm nghẽn

Có thể mô tả bế tắc bằng đồ thị phụ thuộc:

```text
Client READ(response)
       |
       | response chỉ được server tạo sau khi nhận request
       v
Server READ(request)
       |
       | request chỉ được client tạo sau khi nhận response
       v
Client READ(response)       (chu trình không có sự kiện khởi động)
```

Cách sửa là **phá chu trình** bằng một bước gửi đầu tiên được chỉ định. Ví dụ, nếu client chủ động yêu cầu công việc, đặt "client gửi request" làm sự kiện đầu tiên. Nếu server cần công bố challenge/greeting ngay khi chấp nhận kết nối, đặt "server gửi greeting" làm bước đầu tiên, rồi mới chờ request từ client.

Không nên xử lý bế tắc bằng cách cho cả hai phía `Thread.sleep(100)`. Ngủ chỉ thay đổi thời điểm; mỗi phía vẫn đợi cùng điều kiện. Tương tự, đẩy toàn bộ xử lý sang thread mới không tự sửa hợp đồng gửi/nhận. Thread tách riêng giúp hai chiều hoạt động đồng thời khi protocol thật sự yêu cầu, nhưng vẫn phải có framing, trạng thái và điều kiện hoàn tất.

## 4. Quy định thứ tự trao đổi bằng một hợp đồng protocol

### 4.1. Request/response: client bắt đầu

Ví dụ giao thức dạng **mỗi thông điệp một dòng UTF-8**, với hai lệnh `PING` và `PONG`. Điều kiện: payload không chứa newline, client gửi một request tại một thời điểm.

```text
Bên Client                                 Bên Server
CONNECT ---------------------------------> ACCEPT
WRITE "PING\n"
FLUSH (đẩy buffer Java) ----------------> READ LINE = "PING"
WAIT / READ LINE                          VALIDATE "PING"
                                          WRITE "PONG\n"
READ LINE = "PONG" <--------------------- FLUSH
VALIDATE RESPONSE                         READY FOR NEXT REQUEST / CLOSE
```

Đặc tả tối thiểu:

1. **Kết nối:** client kết nối; server `accept()`. Hai bên thống nhất charset UTF-8.
2. **Đơn vị thông điệp:** một request/response kết thúc bằng newline; không dùng newline bên trong payload trừ khi đã có quy tắc escape.
3. **Lượt gửi:** sau khi connect, **client viết đầy đủ request và flush trước khi đọc**; server đọc đủ request trước khi viết response.
4. **Lượt trả lời:** server ghi response, newline và flush; client đọc một dòng, kiểm tra nội dung và kết thúc lượt.
5. **Lỗi và kết thúc:** quy định timeout, EOF, frame lỗi và cách đóng; socket có thể tiếp tục phục vụ lượt sau nếu giao thức cho phép.
6. **Mở rộng:** nếu có nhiều request in-flight, thêm request ID, correlation, quy định thứ tự/trạng thái, hoặc dùng một reader loop duy nhất để định tuyến response.

Bảng trạng thái có thể dùng khi triển khai:

| Vai trò | Trạng thái | Hành động hợp lệ | Trạng thái tiếp |
| --- | --- | --- | --- |
| Client | `CONNECTED` | Write full request + delimiter + flush | `WAIT_RESPONSE` |
| Client | `WAIT_RESPONSE` | Read full response hoặc xử lý timeout/EOF | `READY` hoặc `FAILED/UNKNOWN` |
| Server | `WAIT_REQUEST` | Read full framed request | `PROCESSING` |
| Server | `PROCESSING` | Validate/execute và write full response + flush | `WAIT_REQUEST` hoặc `CLOSED` |

Việc định nghĩa trạng thái giúp review code: nếu ở `CONNECTED` client đọc trước khi gửi request, hành vi ấy trái với hợp đồng. Nếu server chờ một thông điệp mà client không bao giờ gửi ở trạng thái hiện hành, giao thức có lỗ hổng.

### 4.2. Handshake: server bắt đầu

Có giao thức ngược lại, server chủ động gửi lời chào hoặc challenge:

```text
Server                                Client
accept()
WRITE "READY\n", FLUSH ------------> READ "READY"
READ "AUTH ...\n" <---------------- WRITE "AUTH ...\n", FLUSH
VALIDATE, WRITE "OK\n", FLUSH -----> READ "OK"
```

Điều này cũng hợp lệ. Lỗi xảy ra khi server được lập trình theo "client nói trước" còn client lại theo "server nói trước". Cả hai phía và mọi phiên bản client/server phải dùng **cùng một hợp đồng**. Nếu protocol có phiên bản, cần quy định rõ bên nào gửi version negotiation message và gửi lúc nào; không dựa vào suy đoán của từng endpoint.

### 4.3. Hai chiều chủ động (full-duplex)

TCP hỗ trợ cả hai chiều đồng thời: chẳng hạn chat hoặc server push. Khi đó, có thể có **một luồng đọc dài hạn** ở mỗi đầu và một cơ chế ghi độc lập. Không cần đợi ACK trước mọi message nếu protocol cho phép concurrency, nhưng:

- Reader phải biết đóng khung thông điệp; writer không được gửi hai nửa frame xen lẫn từ các thread khác nhau.
- Cần đồng bộ/serialize việc ghi cùng socket hoặc có một writer queue.
- ACK/response cần request ID để gắn với yêu cầu đã gửi; không cho hai thread tự ý cùng `read()` rồi "tranh" response của nhau.
- Backpressure và giới hạn queue phải rõ, vì peer có thể đọc chậm.
- Việc close, cancel, EOF và xử lý lỗi phải đánh thức/giải phóng các bên đang chờ.

Hai phía **đều write trước rồi read** không luôn an toàn nếu mỗi bên cố ghi một lượng lớn dữ liệu vượt dung lượng buffer mà không đọc: cả hai `write()` vẫn có thể chờ. Giao thức tương tác đồng thời cần thiết kế để phía nhận tiếp tục drain input.

## 5. Chương trình Java 17+ tái hiện lỗi và cách sửa

Ví dụ thực nghiệm dùng loopback `127.0.0.1`/localhost theo địa chỉ trả về từ `InetAddress.getLoopbackAddress()`. Nó tạo **hai kết nối độc lập**:

- Lần 1: client và server đều đọc trước, **không ai gửi**. Cả hai nhận `SocketTimeoutException` sau khi chờ, minh họa circular wait. Cả client và server vẫn giữ socket mở tới khi hai kết quả được thu thập để tránh biến một phía thành EOF sớm.
- Lần 2: client gửi `PING` + newline + flush rồi đọc; server đọc `PING`, gửi `PONG` + newline + flush. Chuỗi trao đổi hoàn thành.
- `ExecutorService` chỉ để thực thi server cùng lúc với client trong **một JVM minh họa**, không thay cho protocol. Future giúp phát hiện lỗi worker. Không cần truy cập internet.

**Tệp `ReadReadProtocolDemo.java`:**

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class ReadReadProtocolDemo {
    private static String readWithTimeout(Socket socket)
            throws IOException {
        socket.setSoTimeout(800);
        BufferedReader input = new BufferedReader(
                new InputStreamReader(socket.getInputStream(),
                        StandardCharsets.UTF_8));
        try {
            String line = input.readLine();
            return line == null ? "EOF" : line;
        } catch (SocketTimeoutException e) {
            return "TIMEOUT";
        }
    }

    private static void demonstrateWrongOrder() throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 50, InetAddress.getLoopbackAddress())) {
            listener.setSoTimeout(4000);
            ExecutorService worker = Executors.newSingleThreadExecutor();
            try {
                Future<String> server = worker.submit(() -> {
                    try (Socket peer = listener.accept()) {
                        return readWithTimeout(peer);
                    }
                });
                try (Socket client = new Socket(
                        InetAddress.getLoopbackAddress(),
                        listener.getLocalPort())) {
                    String clientResult = readWithTimeout(client);
                    String serverResult = server.get(4, TimeUnit.SECONDS);
                    System.out.println("BAD client read-first: " + clientResult);
                    System.out.println("BAD server read-first: " + serverResult);
                }
            } finally {
                worker.shutdownNow();
            }
        }
    }

    private static void demonstrateCorrectOrder() throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 50, InetAddress.getLoopbackAddress())) {
            listener.setSoTimeout(4000);
            ExecutorService worker = Executors.newSingleThreadExecutor();
            try {
                Future<String> server = worker.submit(() -> {
                    try (Socket peer = listener.accept()) {
                        peer.setSoTimeout(3000);
                        BufferedReader input = new BufferedReader(
                                new InputStreamReader(peer.getInputStream(),
                                        StandardCharsets.UTF_8));
                        BufferedWriter output = new BufferedWriter(
                                new OutputStreamWriter(peer.getOutputStream(),
                                        StandardCharsets.UTF_8));
                        String request = input.readLine();
                        if (!"PING".equals(request)) {
                            throw new IOException("Invalid request");
                        }
                        output.write("PONG");
                        output.newLine();
                        output.flush();
                        return request;
                    }
                });
                try (Socket client = new Socket(
                        InetAddress.getLoopbackAddress(),
                        listener.getLocalPort())) {
                    client.setSoTimeout(3000);
                    BufferedWriter output = new BufferedWriter(
                            new OutputStreamWriter(client.getOutputStream(),
                                    StandardCharsets.UTF_8));
                    BufferedReader input = new BufferedReader(
                            new InputStreamReader(client.getInputStream(),
                                    StandardCharsets.UTF_8));
                    output.write("PING");
                    output.newLine();
                    output.flush();
                    String reply = input.readLine();
                    if (!"PONG".equals(reply)) {
                        throw new IOException("Invalid response");
                    }
                    System.out.println("GOOD server read: "
                            + server.get(4, TimeUnit.SECONDS));
                    System.out.println("GOOD client read: " + reply);
                }
            } finally {
                worker.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        demonstrateWrongOrder();
        demonstrateCorrectOrder();
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ReadReadProtocolDemo.java
java ReadReadProtocolDemo
```

Stdout của lần chạy thành công:

```text
BAD client read-first: TIMEOUT
BAD server read-first: TIMEOUT
GOOD server read: PING
GOOD client read: PONG
```

Phân tích:

- Hai dòng `BAD` không phải mất gói: **không có byte nào được chủ động gửi** trên kết nối đầu tiên. Timeout chỉ giúp phát hiện việc chờ thay vì treo mãi; chương trình không thể "tự sửa" lỗi gửi/nhận nếu thứ tự không được thay đổi.
- Server được đặt `setSoTimeout(4000)` cho `accept()` và socket của mỗi peer có read timeout riêng. Với `readLine()`, timeout xảy ra khi chưa đọc được dòng hoàn chỉnh trong thời hạn chờ đọc tương ứng.
- Ở phiên đúng, client **write → newline → flush → read**; server **read → validate → write → newline → flush**. Vai trò đảo nhau nhưng không có chờ vòng.
- `server.get(...)` dùng để thu kết quả và truyền lỗi từ server thread về main. Việc gọi `get()` **không phải** application ACK; client đã nhận `PONG` qua input socket trước khi in kết quả.
- Thời gian chờ 800 ms, 3000 ms và 4000 ms chỉ phục vụ bài demo. Trong môi trường bận, có thể cần cấu hình hợp lý hơn; giá trị timeout là chính sách vận hành, không phải thứ tự protocol.
- Server và client dùng cùng UTF-8. `BufferedWriter.newLine()` ghi ký tự kết thúc dòng phù hợp nền tảng, và `BufferedReader.readLine()` nhận các dạng line ending phổ biến. Định dạng production nên ấn định delimiter chuẩn, ví dụ CRLF hoặc LF, để các ngôn ngữ/hệ điều hành thực hiện thống nhất.

## 6. Quy định ranh giới thông điệp trước khi quy định lượt đọc

Một thỏa thuận "client ghi trước, server đọc sau" vẫn chưa đủ nếu **server không biết request đã hoàn chỉnh chưa**. Có ba kiểu framing thông dụng:

| Kiểu framing | Cách kết thúc thông điệp | Điều cần thống nhất |
| --- | --- | --- |
| Delimiter (ví dụ newline) | `\n`/`\r\n` kết thúc frame | Encoding, escape delimiter trong payload, giới hạn dòng |
| Length prefix | Gửi số byte N trước, sau đó đúng N byte | Kiểu số/endianness, giới hạn N, đọc đúng đủ N |
| Fixed size | Mỗi frame dài chính xác K byte | K cố định, padding, version, cách phân biệt dữ liệu thật và phần đệm |

**Line-based protocol:** `write("PING")` không tự tạo một dòng. Phải gửi delimiter bằng `write("\n")` hoặc `newLine()`, rồi `flush()` nếu stream có buffer. Nếu server đọc `readLine()` trong khi client chỉ viết `PING` và đợi ACK, server sẽ tiếp tục chờ dấu kết thúc dòng.

**Length-prefix protocol:** mã giả sau là một *mảnh code bên trong phương thức có stream tương ứng*; người đọc phải xử lý `IOException`:

```java
// Sender
byte[] payload = "PING".getBytes(StandardCharsets.UTF_8);
DataOutputStream out = new DataOutputStream(
        new BufferedOutputStream(socket.getOutputStream()));
out.writeInt(payload.length);  // 4 byte, big-endian
out.write(payload);
out.flush();

// Receiver (trên socket phía bên kia)
DataInputStream in = new DataInputStream(
        new BufferedInputStream(peerSocket.getInputStream()));
int length = in.readInt();
if (length < 0 || length > 64 * 1024) {
    throw new IOException("Invalid frame length");
}
byte[] message = new byte[length];
in.readFully(message);
String text = new String(message, StandardCharsets.UTF_8);
```

**Chú ý:** `DataOutputStream.writeInt` và `DataInputStream.readInt` dùng dạng số 32 bit big-endian; giới hạn độ dài phải kiểm tra trước khi cấp phát buffer. Nếu sender báo N byte nhưng chỉ phát N−1 byte rồi tiếp tục chờ ACK, receiver `readFully` sẽ đợi byte cuối. Không đồng nhất "N ký tự" và "N byte UTF-8": các ký tự Unicode có thể tốn nhiều byte.

Không trộn những cách framing khác nhau trên cùng hai đầu kết nối, chẳng hạn sender dùng `DataOutputStream.writeUTF` (modified UTF-8 với prefix hai byte) nhưng receiver lại đọc `readInt` bốn byte rồi payload UTF-8 chuẩn.

**EOF-delimited protocol:** Nếu hợp đồng nói "request kết thúc khi client đóng chiều gửi", client có thể flush buffer rồi gọi `socket.shutdownOutput()`. Server đọc tới EOF, xử lý rồi trả response qua chiều còn mở. Tuy nhiên, phía client **không được chờ response trước khi shutdownOutput()` trong protocol này**, vì server chưa thấy EOF để kết thúc request. `shutdownOutput` là half-close phía gửi, khác với `socket.close()` đóng toàn bộ socket. EOF là ranh giới truyền dữ liệu, không chứng minh business operation đã thành công.

## 7. Chờ đọc, timeout và đóng kết nối: ba loại tín hiệu khác nhau

Khi đọc qua socket, cần xử lý tách bạch:

- **Có message hoàn chỉnh:** decoder/framer đã lấy đủ dữ liệu theo protocol; mới được chuyển state sang PROCESSING hay RECEIVED_RESPONSE.
- **Đọc trả `-1` hoặc `BufferedReader.readLine()` trả `null`:** peer đã đóng chiều gửi một cách có trật tự và không còn dữ liệu; đây là EOF. EOF có thể hợp lệ nếu protocol dùng nó làm delimiter, hoặc là lỗi "peer đóng quá sớm" khi còn chờ frame.
- **`SocketTimeoutException`:** không nhận được dữ liệu đủ để thao tác đọc hoàn tất trong thời hạn đã đặt; **không chứng minh peer chưa từng xử lý request**.
- **`IOException` khác:** kết nối có vấn đề hoặc I/O thất bại; có thể đã gửi/nhận một phần dữ liệu. Trạng thái transaction cần được đánh giá theo ứng dụng.
- **Không đặt timeout:** lời gọi blocking có thể đợi vô hạn; production thường cần read timeout và deadline bao trùm cả request.

`Socket.setSoTimeout(3000)` giới hạn thời gian **một thao tác đọc blocking**, không phải deadline trọn một request nhiều frame và không tạo write timeout. Khi yêu cầu có nhiều lần đọc, phải có **deadline end-to-end** riêng, nếu không phía kia có thể gửi từng ít dữ liệu và kéo dài tổng thời gian.

Đối với `Socket.connect(SocketAddress, timeout)`, timeout là cho bước thiết lập kết nối; nó không thay thế `SO_TIMEOUT` khi đọc. Nếu `write()` cũng có nguy cơ block do backpressure, cần thiết kế bất đồng bộ/concurrent I/O, giới hạn kích thước, quản lý queue và timeout ở cấp giao thức hoặc tầng I/O thích hợp; không suy ra `setSoTimeout` bảo vệ mọi thao tác.

Bộ đệm ứng dụng và TCP buffer là khác nhau. `flush()` thành công chỉ đẩy dữ liệu khỏi các lớp buffer đang sử dụng theo hợp đồng stream; nó **không phải xác nhận server đã đọc/xử lý**. Phải đợi application-level ACK/response theo semantic do protocol định nghĩa.

## 8. Đặt tên các trạng thái chờ để phát hiện lỗi sớm

Nếu thêm log hay metrics, nên ghi theo request ID và phase:

```text
client(42) CONNECTED
client(42) WRITE_START
client(42) REQUEST_FLUSHED
client(42) WAIT_RESPONSE
server(42) REQUEST_FRAME_COMPLETE
server(42) PROCESSING
server(42) RESPONSE_FLUSHED
client(42) RESPONSE_RECEIVED
```

Một số cặp dấu hiệu:

| Quan sát | Khả năng cần kiểm tra ngay |
| --- | --- |
| Cả hai phía log `WAIT_READ`, không có `WRITE_START` | Hai bên đều đợi bên kia nói trước |
| Client `WRITE_START` nhưng không có `REQUEST_FLUSHED` | Buffer, `write` bị chặn, I/O lỗi hoặc code không đến được flush |
| Client `REQUEST_FLUSHED`; server chỉ log `WAIT_FRAME` | Delimiter/length thiếu, mismatch charset/codec, server đọc sai connection |
| Server `RESPONSE_FLUSHED`; client chưa có `RESPONSE_RECEIVED` | Chờ sai frame, nhầm request ID, timeout/connection, response chưa hoàn chỉnh |
| Client đợi response; server log `WAIT_EOF` | Hai bên không đồng ý request kết thúc bằng delimiter hay EOF |
| Cả hai thread đang blocked ở `write` | Phía nhận không drain stream; có thể cần concurrent reader/backpressure |

Thread dump (ví dụ `jstack` hoặc `jcmd <pid> Thread.print`) có thể chỉ ra thread đang chờ socket read/write. Tên method nội bộ thay đổi theo phiên bản JDK, vì vậy tập trung vào **stack trace, request ID và state machine** thay vì trông đợi một tên hàm hệ thống cố định.

Packet capture có thể cho thấy TCP segment/ACK, nhưng **TCP ACK không phải application ACK** và không chứng minh server đã đọc frame hoặc commit nghiệp vụ. Cần log/trace ở tầng ứng dụng để biết server đạt trạng thái nào. Khi ghi log payload, tránh lộ mật khẩu, token hoặc dữ liệu nhạy cảm; trạng thái, kích thước và ID thường đủ để phân tích thứ tự.

## 9. Xử lý request đồng thời và phản hồi trễ

Giao thức đơn giản "gửi một request rồi đọc một response" dễ hiểu và tránh trộn response. Khi mở rộng:

1. **Có nhiều request trên cùng socket:** kèm `requestId` ở cả request và response, tránh nhầm response của yêu cầu A thành của B. Nếu server có thể trả khác thứ tự, client phải định tuyến theo ID thay vì dựa vào thứ tự gửi.
2. **Chỉ có một reader phân loại message cho mỗi hướng:** không để nhiều thread tùy ý cùng đọc một `InputStream` rồi mỗi thread "hy vọng" bắt trúng ACK của mình. Reader trung tâm phân phối cho các pending requests bằng ID hoặc queue.
3. **Serialize writer:** nếu nhiều thread cùng ghi, phải bảo đảm từng frame được giữ nguyên thứ tự byte; tránh các `write` phần đầu/body của các request xen kẽ nhau.
4. **Server push:** có thể nhận message tự phát khi đang chờ response, nên decoder cần phân biệt type `EVENT`, `RESPONSE`, `ERROR`.
5. **Giới hạn tài nguyên:** giới hạn số message in-flight, kích thước frame, queue, timeout và tốc độ gửi; có cơ chế cancel/close phù hợp.
6. **Retry:** timeout chờ response có thể xảy ra sau khi server đã xử lý xong nhưng phản hồi mất; dùng idempotency key/truy vấn trạng thái khi nghiệp vụ có side effect. Không tự động kết luận "chưa xử lý" vì `read()` timeout.

Cách đơn giản hóa trước khi thêm concurrency: kiểm chứng một lượt request/response trên một connection, một reader và một writer theo hợp đồng rõ ràng. Khi mở rộng full-duplex, giữ nguyên framing, trạng thái và ngữ nghĩa ACK đã xác nhận.

## 10. Các lỗi thường gặp và cách sửa

| Lỗi trong code/giao thức | Vì sao sai? | Hướng sửa |
| --- | --- | --- |
| Client và server đều gọi `readLine()` đầu tiên | Circular wait: không ai gửi | Chỉ định vai trò chủ động gửi/chào |
| Ghi `"PING"` rồi gọi `readLine()` ở client | Server có thể đợi newline | Thêm delimiter đúng protocol, rồi flush |
| Ghi đủ request nhưng quên `flush()` của `BufferedWriter` | Byte còn trong Java buffer | Flush sau khi đã tạo frame hoàn chỉnh |
| Server chờ `read() == -1`, client chờ ACK và giữ output mở | Không có EOF để server bắt đầu xử lý | Thống nhất framing; nếu thật sự EOF-delimited thì flush + half-close |
| Client `read()` một lần và cho đó là toàn bộ response | TCP không có message boundary | Dùng length prefix/delimiter và đọc đủ |
| Server giữ response trong buffer, rồi quay lại `read()` | Client chưa thấy response để tiếp tục | Flush response trước khi chờ lượt sau |
| Gọi `Thread.sleep(...)` để "đợi đủ byte" | Timing không chứng minh frame hoàn chỉnh | Framing và timeout rõ ràng |
| Gọi `InputStream.available() == 0` để kết luận peer chưa gửi hoặc đã xong | `available` chỉ ước lượng byte đọc ngay không block, không báo message complete/EOF | Đọc theo framing; phân biệt EOF, timeout và lỗi |
| Tăng timeout rất lớn khi hai phía đợi nhau | Chỉ làm bế tắc lâu hơn | Sửa trạng thái gửi/nhận |
| Gọi `socket.close()` sau `write()` và cho rằng đối tác xử lý xong | Close/EOF không phải business ACK | Định nghĩa và đọc phản hồi ở tầng ứng dụng |
| Dùng hai reader tự đọc ACK trên cùng socket | Có thể nuốt nhầm response | Một reader định tuyến theo correlation ID |
| Cho cả hai bên ghi một buffer khổng lồ rồi mới đọc | Có thể block vì backpressure | Thiết kế full-duplex, drain input đồng thời và giới hạn bộ đệm |

## 11. Bài tập áp dụng

**Bài 1 — Tìm bế tắc:** Client gọi `reader.readLine()` đợi `READY` trước khi gửi `AUTH`; server gọi `reader.readLine()` đợi `AUTH` trước khi gửi `READY`. Hãy vẽ mối phụ thuộc và sửa sao cho có một bên nói đầu tiên.

**Bài 2 — Phát hiện frame thiếu:** Client gọi `writer.write("HELLO")`, `writer.flush()` rồi `readLine()` đợi ACK. Server cũng dùng `readLine()`. Tại sao server vẫn chờ dù client đã flush? Sửa một dòng code.

**Bài 3 — Phân biệt byte và message:** Client gửi prefix độ dài 12 byte rồi chỉ gửi 5 byte payload. Server gọi `readFully(new byte[12])`. Nếu client chờ response, hai bên có thể rơi vào tình trạng gì? Khi nào server có thể báo lỗi?

**Bài 4 — EOF protocol:** Server đọc cho tới EOF trước khi gửi response; client gửi request rồi đợi response. Client phải làm gì để kết thúc chiều gửi mà vẫn đọc được response trên cùng TCP socket?

**Bài 5 — Full-duplex:** Hai request A và B đồng thời trên một socket, server trả B trước A. Giải thích vì sao hai thread cùng gọi `readLine()` để chờ ACK riêng có thể nhận nhầm dữ liệu. Nêu cấu trúc giao thức và mô hình reader phù hợp.

**Đáp án gợi ý:**

1. Nếu server đòi AUTH trước còn client đòi READY trước thì không bên nào gửi. Chọn server gửi `READY\n` rồi flush, client nhận xong mới gửi `AUTH\n`; hoặc đổi đặc tả thành client gửi AUTH trước và sửa cả hai.
2. `flush` không tự thêm newline. Sau `write("HELLO")` cần thêm `writer.newLine()` **trước** `flush()`; server mới có frame hoàn chỉnh.
3. Server chờ thêm 7 byte; client chờ ACK, tạo chờ vòng. Server chỉ dừng khi nhận đủ byte, EOF làm `readFully` báo lỗi hoặc socket read timeout/lỗi khác.
4. Flush các wrapper Java rồi gọi `socket.shutdownOutput()` để server thấy EOF; client tiếp tục đọc input cho tới khi có response, theo protocol cho phép half-close.
5. Hai reader tranh một luồng byte, một thread có thể nhận frame của request khác. Thêm `requestId` và một reader loop định tuyến reply theo ID.

## Tài liệu tham khảo

- [Java SE 17 — `Socket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): `getInputStream`, `getOutputStream`, `setSoTimeout`, `shutdownOutput`, `setTcpNoDelay`.
- [Java SE 17 — `ServerSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): `accept`, `setSoTimeout` và listener.
- [Java SE 17 — `BufferedReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html): `readLine()` và quy tắc kết thúc dòng.
- [Java SE 17 — `BufferedWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html): `newLine()` và `flush()`.
- [Java SE 17 — `DataInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readInt()`, `readFully()`.
- [Java SE 17 — `OutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): semantics của `write`/`flush`.
