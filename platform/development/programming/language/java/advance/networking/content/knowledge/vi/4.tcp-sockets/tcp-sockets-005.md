# Đọc InputStream, ghi OutputStream và nhận biết kết thúc luồng TCP

## Mục tiêu

Khi làm việc với `java.net.Socket`, hai phía giao tiếp chủ yếu thông qua `InputStream` và `OutputStream`. Đọc và ghi có vẻ đơn giản, nhưng lỗi mạng khó tìm thường xuất phát từ việc hiểu nhầm ba điều:

1. **TCP là luồng byte có thứ tự**, không phải hàng đợi các thông điệp độc lập. Ranh giới từng lần gọi `write()` ở bên gửi **không** biến thành ranh giới từng lần `read()` ở bên nhận.
2. **Chưa có dữ liệu** khác với **đã hết luồng**. Một lần `read()` có thể phải chờ; nhận `-1` có nghĩa đầu gửi đã kết thúc chiều truyền đó theo cách mà input stream quan sát được, sau khi dữ liệu còn trong luồng đã được đọc hết.
3. **Kết thúc luồng** khác với **kết thúc một thông điệp**. Ứng dụng cần quy tắc đóng khung dữ liệu (*framing*): độ dài, ký tự phân cách hoặc dùng EOF nếu mỗi kết nối chỉ mang một thông điệp.

Bài học đi từ hành vi chính xác của `read`/`write` đến đóng socket, half-close với `shutdownOutput()`, timeout và các ví dụ Java 17+ chạy bằng loopback trên một máy.

## 1. Socket cung cấp hai chiều truyền byte độc lập

Sau khi client gọi `Socket.connect(...)` và server `ServerSocket.accept()` thành công, mỗi `Socket` đã kết nối có:

- `socket.getInputStream()`: đọc **byte do phía bên kia gửi đến**.
- `socket.getOutputStream()`: ghi **byte muốn gửi cho phía bên kia**.

Ở phía client, ghi vào output của client làm byte đi tới input của server; chiều ngược lại cũng vậy. Đây là truyền thông **full-duplex**: hai phía có thể vừa gửi vừa nhận.

```text
Client socket                              Server socket
┌──────────────────┐                      ┌──────────────────┐
│ OutputStream     │ ───── byte ────────► │ InputStream      │
│ InputStream      │ ◄───── byte ──────── │ OutputStream     │
└──────────────────┘                      └──────────────────┘

TCP giữ thứ tự byte trong từng chiều.
Hai chiều có thể kết thúc riêng (half-close).
Không có dấu phân cách message tự động giữa các lần write().
```

Một socket đã kết nối có địa chỉ/port local và remote; một server có thể nhận nhiều socket đã kết nối trên cùng một listening port. `ServerSocket` dùng để chờ kết nối mới, còn hai stream đọc/ghi của `Socket` dùng để trao đổi dữ liệu **trên một kết nối đã được chấp nhận**.

Các stream này làm việc với **byte**. Nếu nội dung là text, bạn phải thống nhất encoding (thường là UTF-8), cách chia message và cách báo khi một message đã hoàn tất.

## 2. `InputStream.read()`: giá trị trả về mới là bằng chứng

### 2.1. Đọc từng byte

```java
InputStream in = socket.getInputStream();
int value = in.read();
```

`read()` trả về một số kiểu `int`:

| Kết quả | Ý nghĩa |
|---|---|
| `0` đến `255` | Đọc được **một byte**; `0` là byte dữ liệu hợp lệ, không phải EOF |
| `-1` | **End-of-stream (EOF)**: không còn byte nào để đọc trong luồng này |
| Ném `IOException` | Có lỗi I/O; có thể là kết nối reset, socket đóng hoặc lỗi mạng |
| Chưa trả về | `read()` đang chờ byte/EOF/lỗi; không đồng nghĩa dữ liệu đã hết |

Không ép kết quả `read()` về `byte` trước khi kiểm tra `-1`, vì `byte` trong Java là signed (`-128`..`127`) và có thể làm mất khả năng phân biệt EOF với giá trị dữ liệu.

Ví dụ thuần bộ nhớ, chạy được độc lập và có output xác định:

**Tệp `ReadByteValues.java`**

```java
import java.io.ByteArrayInputStream;
import java.io.InputStream;

public class ReadByteValues {
    public static void main(String[] args) throws Exception {
        byte[] data = {(byte) 0xFF, 0x00};
        try (InputStream in = new ByteArrayInputStream(data)) {
            System.out.println(in.read());
            System.out.println(in.read());
            System.out.println(in.read());
        }
    }
}
```

```bash
javac -encoding UTF-8 ReadByteValues.java
java ReadByteValues
```

```text
255
0
-1
```

`0xFF` là một byte có giá trị unsigned 255 nên `read()` trả 255; byte `0x00` trả 0; **chỉ lần thứ ba** trả `-1`. Đây là minh họa quy tắc của `InputStream`, không có kết nối TCP trong ví dụ này.

### 2.2. Đọc theo buffer

```java
byte[] buffer = new byte[4096];
int n = in.read(buffer);
if (n == -1) {
    // Đã nhận EOF.
} else {
    // Chỉ các byte buffer[0..n-1] là dữ liệu của lần đọc này.
}
```

Khi buffer có độ dài dương, `read(buffer)` thông thường sẽ chờ cho tới khi có ít nhất một byte, EOF hoặc lỗi; một lần thành công có thể trả **bất kỳ số byte từ 1 đến `buffer.length`**. Với yêu cầu đọc có độ dài bằng 0, API có thể trả `0` mà không đọc byte nào; không lấy trường hợp đặc biệt đó làm thông điệp mạng.

**Không được giả định** cứ client gọi `write(bytes)` với 4.096 byte thì server sẽ nhận đúng 4.096 byte trong một lần `read(buffer)`. Hệ điều hành, lịch gửi, TCP, buffer và thời điểm đọc có thể chia/gộp dữ liệu; TCP chỉ bảo đảm thứ tự byte và cơ chế truyền tin cậy trong điều kiện kết nối thành công.

Cách tích lũy đúng khi **protocol quy định EOF chính là cuối thông điệp**:

```java
// Đoạn minh họa nằm trong một hàm đã có InputStream in.
byte[] buffer = new byte[4096];
int n;
while ((n = in.read(buffer)) != -1) {
    consume(buffer, 0, n); // consume là hàm ứng dụng phải tự định nghĩa.
}
```

Đoạn trên chỉ minh họa vòng lặp; **không phải một chương trình độc lập** vì `consume(...)` là hàm của ứng dụng. Dùng `ByteArrayOutputStream`, xử lý streaming hoặc parser tùy nhu cầu; với dữ liệu từ mạng phải đặt giới hạn kích thước hợp lý thay vì tích lũy vô hạn.

### 2.3. Những cách đọc sai

- **Sai:** `if (in.read(buffer) < buffer.length)` thì hết message. Một lần đọc thiếu buffer chỉ có nghĩa lần đọc ấy trả được ít byte hơn dung lượng.
- **Sai:** `if (in.available() == 0)` thì EOF. `available()` là ước lượng số byte có thể đọc ngay mà không block; `0` vẫn có thể là kết nối đang chờ dữ liệu tương lai.
- **Sai:** `if (socket.isConnected())` thì peer vẫn đang online. `isConnected()` phản ánh lịch sử trạng thái connect của socket, không phải phép đo liveness thời gian thực.
- **Sai:** cứ đọc đúng một lần là nhận hết request. TCP có thể trả message thành nhiều phần; phải có framing.
- **Sai:** xử lý `SocketTimeoutException` như EOF. Timeout là việc **chờ quá lâu**, không phải tín hiệu đầu gửi đã đóng chiều truyền.

## 3. `OutputStream.write()`: gửi byte, không gửi “message có viền”

Các overload thường dùng:

```java
OutputStream out = socket.getOutputStream();
out.write(65);                     // Một byte: giá trị A trong ASCII.
out.write(new byte[] {66, 67});    // Hai byte: B, C.
out.flush();
```

Ở phía đọc, TCP có thể cho bạn nhận `ABC` trong một lần `read` hoặc chia thành các đoạn. `write` được gọi ba lần hay một lần không tạo ra ranh giới thông điệp có thể nhìn thấy ở đầu nhận.

**Ý nghĩa của `write()` trả về:** bytes đã được giao cho tầng output của Java và hệ thống I/O; nó **không chứng minh** phía bên kia đã nhận, đọc, xác thực hay xử lý ứng dụng. Ghi vào socket có thể block do giới hạn bộ đệm/flow control; lỗi đóng đột ngột của peer đôi khi chỉ lộ ra ở một lần ghi/đọc sau đó.

### 3.1. Khi nào cần `flush()`?

Có hai tầng thường dễ lẫn:

- `Socket.getOutputStream()` trả stream gửi tới socket; nó không tạo bộ đệm `BufferedOutputStream` của Java theo mặc định. `flush()` trên raw stream không hề tạo dấu kết thúc message.
- Nếu bạn tự bọc `BufferedOutputStream` hoặc `BufferedWriter`, dữ liệu có thể nằm trong **bộ đệm phía Java**. Phải `flush()` vào thời điểm protocol cần peer bắt đầu xử lý; nếu chờ đóng buffer trong khi vẫn đợi response, chương trình có thể bị treo.

`flush()` đẩy dữ liệu đang giữ trong buffer của Java xuống stream bên dưới; **không đồng nghĩa TCP đã được ACK bởi peer hay ứng dụng bên kia đã đọc xong**. Nó cũng **không gửi EOF**, không đóng kết nối và không tự tạo newline/length prefix.

Ví dụ khi hai bên thống nhất message kết thúc bằng dấu xuống dòng:

```java
BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(socket.getOutputStream(),
                java.nio.charset.StandardCharsets.UTF_8));

writer.write("PING");
writer.newLine(); // Ký tự xuống dòng thuộc giao thức text của ví dụ.
writer.flush();   // Đẩy dữ liệu từ BufferedWriter vào socket.
```

Đây là **đoạn minh họa**, giả định biến `socket` đã kết nối. Phía nhận có thể dùng `BufferedReader.readLine()`. Không dùng `newLine()` cho giao thức nhị phân hoặc giao thức vốn không định nghĩa delimiter này.

### 3.2. Coi chừng “đóng writer để gửi xong request”

`BufferedWriter.close()` đóng writer và stream bên dưới. Với stream lấy từ `Socket`, đóng stream **đóng socket**, khiến cả chiều đọc response không còn sử dụng bình thường được. Nếu muốn chỉ báo “client gửi hết request” mà **vẫn muốn đọc response trên cùng TCP connection**, dùng framing phù hợp hoặc `socket.shutdownOutput()`, không đóng toàn bộ socket sớm.

`PrintWriter` còn có đặc điểm **không ném `IOException` trực tiếp** ở một số thao tác ghi; cần `checkError()` nếu dùng nó. Với ví dụ debug mạng, `OutputStream`/`BufferedWriter` thường làm lỗi I/O dễ quan sát hơn.

## 4. EOF trong TCP: từ FIN, half-close đến reset

### 4.1. Trường hợp đóng chiều gửi bình thường

Ở một TCP connection, bên A có thể thông báo rằng A **sẽ không gửi thêm byte nào** bằng cách kết thúc chiều output. Trong TCP, kết thúc gửi bình thường thường được biểu thị bằng **FIN**. Bên B vẫn đọc các byte đã đến trước FIN, sau đó `InputStream.read()` trả `-1`.

```text
Client                                 Server
  │  write("HELLO")                      │
  │ ───────────────────────────────────►│  read(...) nhận byte
  │  shutdownOutput()                    │
  │ ─────────────── FIN ────────────────►│  read(...) -> -1 sau khi hết byte
  │                                     │  write("ACK")
  │ ◄───────────────────────────────────│
  │  read(...) nhận "ACK"                │
  │  read(...) -> -1 khi server đóng gửi │
  └─────────────────────────────────────┘
```

**Half-close** nghĩa là một chiều đã kết thúc nhưng chiều còn lại vẫn có thể truyền. Trong Java:

- `socket.shutdownOutput()`: kết thúc chiều **gửi** của socket; byte đã được gửi trước đó đi trước tín hiệu kết thúc. Sau thao tác này, tiếp tục viết vào output stream sẽ gây lỗi I/O.
- `socket.shutdownInput()`: kết thúc **chiều nhận cục bộ**, khiến input stream của socket được đặt ở EOF; dữ liệu tiếp nhận sau đó có thể bị bỏ đi. Đây **không** phải cách thông báo cho peer rằng ta đã gửi xong.
- `socket.close()`: đóng socket; không phải công cụ thích hợp nếu còn cần đọc response. Đóng socket thường chấm dứt việc sử dụng cả input lẫn output.
- `Socket.shutdownOutput()` không được hiểu là “kết thúc một HTTP request” trong HTTP keep-alive; HTTP có quy tắc định khung riêng. Không dùng half-close sau từng message trên kết nối được dự định tái sử dụng.

### 4.2. `-1`, lỗi reset và timeout là ba tín hiệu khác nhau

| Tình huống | Kết quả có thể quan sát ở Java | Cách hiểu |
|---|---|---|
| Peer gửi một phần byte nhưng chưa kết thúc chiều gửi | `read` trả byte đang có, rồi các lần đọc sau có thể chờ | Chưa có EOF |
| Peer gửi FIN bình thường, mọi byte trước FIN đã đọc hết | `read` trả `-1` | Kết thúc luồng đầu vào |
| Peer hoặc mạng hủy kết nối, ví dụ TCP RST | `read`/`write` có thể ném `SocketException` hoặc `IOException` | Lỗi kết nối; không được đồng nhất với EOF sạch |
| Chờ quá lâu sau khi đặt `setSoTimeout` | `SocketTimeoutException` | Chưa có byte/EOF trong khoảng chờ; không tự khẳng định peer đã đóng |
| Ta đóng socket của chính mình | Đọc/ghi trên stream đã đóng có thể gây `SocketException` | Hành động phía local, không phải remote EOF bình thường |

Không suy diễn rằng tất cả hình thức mất mạng đều sớm tạo `-1`. Mất kết nối vật lý “im lặng” có thể làm `read` tiếp tục block khá lâu nếu không có timeout/protocol timeout thích hợp. TCP keepalive (nếu bật và được hệ điều hành hỗ trợ) là cơ chế phát hiện một số peer chết ở tầng TCP, **không** cung cấp ranh giới message và không phải thay thế cho timeout/heartbeat ứng dụng.

### 4.3. Thế nào là “đã hết một message”?

Có ít nhất ba câu hỏi khác nhau:

- **Đã hết dữ liệu đang có ngay lúc này?** Chưa có nghĩa hết message. `available()==0` không trả lời được.
- **Đã hết message theo protocol?** Biết được nhờ delimiter, tiền tố độ dài, kích thước cố định, hoặc parser của giao thức.
- **Peer đã kết thúc hẳn chiều gửi TCP?** Đọc cho tới `-1`. Điều này **có thể** được dùng làm dấu hết một message nếu protocol quy định mỗi chiều gửi một payload rồi kết thúc; không phù hợp cho kết nối có nhiều message tuần tự.

## 5. Java 17+: chứng minh `shutdownOutput()` và EOF bằng chương trình chạy được

Chương trình này mở server trên loopback ở port tạm thời do hệ điều hành chọn, chạy phần server trong một thread và phần client ở main thread. Client ghi hai mảnh byte `HEL` và `LO` rồi gọi `shutdownOutput()`. Server **không giả định ranh giới hai lần write**, đọc cho đến EOF, sau đó trả `ACK` cho client.

Tạo tệp **`SocketHalfCloseDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SocketHalfCloseDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try (ServerSocket server = new ServerSocket()) {
            InetAddress loopback = InetAddress.getLoopbackAddress();
            server.bind(new InetSocketAddress(loopback, 0));
            server.setSoTimeout(3000);

            Future<String> serverResult = executor.submit(() -> {
                try (Socket accepted = server.accept()) {
                    accepted.setSoTimeout(3000);
                    InputStream input = accepted.getInputStream();
                    ByteArrayOutputStream body = new ByteArrayOutputStream();
                    byte[] buffer = new byte[3];
                    int count;

                    while ((count = input.read(buffer)) != -1) {
                        if (body.size() + count > 1024) {
                            throw new IOException("Request too large");
                        }
                        body.write(buffer, 0, count);
                    }

                    OutputStream output = accepted.getOutputStream();
                    output.write("ACK".getBytes(StandardCharsets.UTF_8));
                    output.flush();
                    return body.toString(StandardCharsets.UTF_8);
                }
            });

            try (Socket client = new Socket()) {
                client.connect(
                        new InetSocketAddress(loopback, server.getLocalPort()),
                        3000);
                client.setSoTimeout(3000);

                OutputStream output = client.getOutputStream();
                output.write("HEL".getBytes(StandardCharsets.UTF_8));
                output.write("LO".getBytes(StandardCharsets.UTF_8));
                output.flush();
                client.shutdownOutput();

                InputStream input = client.getInputStream();
                ByteArrayOutputStream reply = new ByteArrayOutputStream();
                int value;
                while ((value = input.read()) != -1) {
                    reply.write(value);
                }

                System.out.println("Client response: "
                        + reply.toString(StandardCharsets.UTF_8));
            }

            System.out.println("Server request: "
                    + serverResult.get(4, TimeUnit.SECONDS));
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc cao hơn:

```bash
javac -encoding UTF-8 SocketHalfCloseDemo.java
java SocketHalfCloseDemo
```

Trong điều kiện socket loopback hoạt động bình thường, stdout **đúng theo thứ tự main thread in**:

```text
Client response: ACK
Server request: HELLO
```

Giải thích:

1. `server.bind(..., 0)` cho hệ điều hành cấp port; vì thế không cần đoán port cố định và không cần hai terminal.
2. Server gọi `read(buffer)` nhiều lần cho đến `-1`. Buffer chỉ 3 byte để nhắc rằng một message 5 byte không thể được bảo đảm nhận đủ trong một lần đọc. Số lần lặp và số byte mỗi lần là chi tiết không xác định.
3. Hai lần client `write()` không tạo hai message. Toàn bộ payload được ghép lại đúng thứ tự thành `HELLO`.
4. `client.shutdownOutput()` giúp server quan sát EOF **mà không phải đóng chiều nhận của client**. Server có thể trả lại `ACK`.
5. Sau khi server ghi reply rồi đóng accepted socket khi ra khỏi `try`, client đọc hết reply và nhận EOF ở chiều của server.
6. `setSoTimeout(3000)` giúp thao tác đọc không treo vô hạn trong ví dụ. Nếu môi trường bị hạn chế hoặc chạy quá chậm, chương trình có thể ném exception; đó là lỗi khi chạy thí nghiệm chứ không phải một dòng stdout chuẩn.
7. Giới hạn 1.024 byte cho request minh họa rằng server không nên đọc payload từ client không tin cậy vào bộ nhớ không giới hạn.

**Quan trọng:** ví dụ dùng **EOF làm dấu hết request** nên mỗi client chỉ gửi một request rồi half-close. Đây là một giao thức demo có chủ đích. Với chat, RPC, HTTP keep-alive hay nhiều message trên cùng connection, bạn phải dùng framing khác.

## 6. Phân biệt ranh giới message với EOF bằng framing

Ba chiến lược phổ biến:

| Framing | Dấu hoàn tất message | Khi nào phù hợp | Rủi ro cần xử lý |
|---|---|---|---|
| **Dựa vào EOF** | Peer kết thúc chiều gửi và `read() == -1` | Một request duy nhất trên mỗi chiều truyền, sau đó gửi response | Không tái sử dụng chiều gửi; dễ deadlock nếu cả hai đợi nhau |
| **Phân cách bằng dòng** | `\n`, `\r\n` hoặc delimiter do protocol quy định | Text command đơn giản: `PING\n`, `QUIT\n` | Payload chứa delimiter cần escaping; giới hạn độ dài; encoding |
| **Tiền tố độ dài** | Đọc header chứa kích thước rồi đọc chính xác số byte payload | Binary/message nhiều bản ghi trên một TCP connection | Byte order, độ dài độc hại, đọc thiếu, overflow và giới hạn bộ nhớ |
| **Parser giao thức chuẩn** | Quy tắc do HTTP, WebSocket, TLS hoặc giao thức khác định nghĩa | Hệ thống thực tế sử dụng giao thức chuẩn | Phải dùng đúng parser/thư viện; không lấy TCP packet làm message |

Đừng giải mã từng mảnh `byte[]` thành `String` khi mỗi lần đọc chưa chứa đầy đủ ký tự UTF-8: một ký tự có thể nằm vắt qua hai lần đọc. Hãy dùng `InputStreamReader` hoặc bộ giải mã xử lý streaming, hoặc tích lũy **một message hoàn chỉnh theo framing** rồi giải mã.

### 6.1. Vì sao `readLine()` không phải lúc nào cũng cần EOF?

`BufferedReader.readLine()` đọc cho đến dấu kết thúc dòng (hoặc EOF), bỏ dấu kết thúc dòng khỏi chuỗi trả về. Với protocol phân cách bằng newline:

- `readLine()` trả `"PING"` khi nhận `PING\n`; nó không cần client đóng kết nối.
- `readLine()` trả `""` với một **dòng trống**; không phải EOF.
- `readLine()` trả **`null`** khi EOF được thấy mà **không còn ký tự nào** để trả. Nếu EOF đến sau một đoạn chữ chưa có dấu xuống dòng, phương thức có thể trả đoạn chữ đó trước, rồi lần tiếp theo mới trả `null`.
- Nếu client ghi `"PING"` mà không gửi dấu xuống dòng, không đóng output và server đang chờ `readLine()`, server có thể tiếp tục đợi. `flush()` đơn lẻ không tự thêm newline.

Đây là lý do phải ghi rõ **hợp đồng delimiter** trong giao thức và giới hạn kích thước dòng; `BufferedReader.readLine()` không tự áp giới hạn kích thước tối đa cho một dòng do peer gửi.

## 7. Java 17+: nhiều message trên cùng kết nối bằng newline

Ví dụ độc lập tiếp theo gửi hai dòng `alpha` và một dòng trống, nhận một phản hồi `ACK 2` **trước khi client đóng socket**. Nó minh họa cách ứng dụng biết đủ hai message mà không cần chờ EOF.

Tạo tệp **`SocketLineMessages.java`**:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SocketLineMessages {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try (ServerSocket server = new ServerSocket()) {
            InetAddress loopback = InetAddress.getLoopbackAddress();
            server.bind(new InetSocketAddress(loopback, 0));
            server.setSoTimeout(3000);

            Future<String[]> messages = executor.submit(() -> {
                try (Socket socket = server.accept()) {
                    socket.setSoTimeout(3000);
                    BufferedReader reader = new BufferedReader(
                            new InputStreamReader(socket.getInputStream(),
                                    StandardCharsets.UTF_8));
                    BufferedWriter writer = new BufferedWriter(
                            new OutputStreamWriter(socket.getOutputStream(),
                                    StandardCharsets.UTF_8));

                    String first = reader.readLine();
                    String second = reader.readLine();
                    writer.write("ACK 2");
                    writer.newLine();
                    writer.flush();
                    return new String[] {first, second};
                }
            });

            try (Socket socket = new Socket()) {
                socket.connect(
                        new InetSocketAddress(loopback, server.getLocalPort()),
                        3000);
                socket.setSoTimeout(3000);

                BufferedWriter writer = new BufferedWriter(
                        new OutputStreamWriter(socket.getOutputStream(),
                                StandardCharsets.UTF_8));
                BufferedReader reader = new BufferedReader(
                        new InputStreamReader(socket.getInputStream(),
                                StandardCharsets.UTF_8));

                writer.write("alpha");
                writer.newLine();
                writer.newLine(); // Một dòng rỗng là message thứ hai.
                writer.flush();

                System.out.println("Client response: " + reader.readLine());
            }

            String[] result = messages.get(4, TimeUnit.SECONDS);
            System.out.println("Server first: " + result[0]);
            System.out.println("Server second empty: " + result[1].isEmpty());
        } finally {
            executor.shutdownNow();
        }
    }
}
```

```bash
javac -encoding UTF-8 SocketLineMessages.java
java SocketLineMessages
```

Stdout khi chạy thành công:

```text
Client response: ACK 2
Server first: alpha
Server second empty: true
```

Giải thích:

- `writer.newLine()` thêm delimiter; `flush()` chuyển dữ liệu từ Java buffer xuống output của socket.
- Server đọc **hai dòng**, không chờ nhận EOF. Dòng thứ hai `""` vẫn là message hợp lệ theo giao thức giả định.
- Server phản hồi rồi đóng socket sau khi return; client đã nhận `ACK 2` và không cần gửi `shutdownOutput()`.
- Server không phân biệt được từng lần TCP `read` và không cần làm điều đó. `BufferedReader` chịu trách nhiệm buffer/giải mã UTF-8, còn **định dạng theo dòng** là quy tắc ứng dụng.
- Đoạn demo giả định số dòng cố định và message nhỏ. Server thực tế phải giới hạn độ dài, xử lý newline trong payload, EOF đột ngột, timeout, nhiều client và lỗi protocol.

**Lưu ý giao thức:** ký tự `newLine()` phụ thuộc platform (ví dụ LF trên nhiều hệ Unix, CRLF trên Windows), trong khi `readLine()` hiểu các kiểu kết thúc dòng phổ biến. Nếu thiết kế một protocol cần byte delimiter cố định trên mọi nền tảng, **ghi rõ delimiter** (ví dụ luôn `\n` bằng `writer.write('\n')`), tránh lệ thuộc vào ký tự xuống dòng mặc định của OS.

## 8. Java 17+: đọc chính xác payload bằng tiền tố độ dài

Đối với dữ liệu nhị phân hoặc text có thể chứa newline, một cách phổ biến là đặt **4 byte số nguyên big-endian** trước payload UTF-8. Bên đọc lấy số độ dài, kiểm tra giới hạn, rồi đọc **đúng số byte**. Dưới đây sử dụng `DataOutputStream.writeInt` và `DataInputStream.readInt`, hai API thống nhất thứ tự byte cho số nguyên.

Tạo tệp **`SocketLengthFrames.java`**:

```java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SocketLengthFrames {
    private static final int MAX_BYTES = 4096;

    private static void sendFrame(DataOutputStream output, String text)
            throws IOException {
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        if (payload.length > MAX_BYTES) {
            throw new IOException("Payload too large");
        }
        output.writeInt(payload.length);
        output.write(payload);
    }

    private static String readFrame(DataInputStream input) throws IOException {
        int length = input.readInt();
        if (length < 0 || length > MAX_BYTES) {
            throw new IOException("Invalid frame length: " + length);
        }
        byte[] payload = new byte[length];
        input.readFully(payload); // Đọc đủ length byte hoặc ném EOFException.
        return new String(payload, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try (ServerSocket server = new ServerSocket()) {
            InetAddress loopback = InetAddress.getLoopbackAddress();
            server.bind(new InetSocketAddress(loopback, 0));
            server.setSoTimeout(3000);

            Future<String[]> messages = executor.submit(() -> {
                try (Socket socket = server.accept()) {
                    socket.setSoTimeout(3000);
                    DataInputStream input =
                            new DataInputStream(socket.getInputStream());
                    DataOutputStream output =
                            new DataOutputStream(socket.getOutputStream());

                    String first = readFrame(input);
                    String second = readFrame(input);
                    sendFrame(output, "ACK");
                    output.flush();
                    return new String[] {first, second};
                }
            });

            try (Socket socket = new Socket()) {
                socket.connect(
                        new InetSocketAddress(loopback, server.getLocalPort()),
                        3000);
                socket.setSoTimeout(3000);
                DataInputStream input =
                        new DataInputStream(socket.getInputStream());
                DataOutputStream output =
                        new DataOutputStream(socket.getOutputStream());

                sendFrame(output, "HELLO");
                sendFrame(output, "JAVA");
                output.flush();
                System.out.println("Client response: " + readFrame(input));
            }

            String[] result = messages.get(4, TimeUnit.SECONDS);
            System.out.println("Server first: " + result[0]);
            System.out.println("Server second: " + result[1]);
        } finally {
            executor.shutdownNow();
        }
    }
}
```

```bash
javac -encoding UTF-8 SocketLengthFrames.java
java SocketLengthFrames
```

Stdout khi TCP loopback hoạt động bình thường:

```text
Client response: ACK
Server first: HELLO
Server second: JAVA
```

**Tại sao chương trình này không chờ EOF giữa hai message?** Server `readFrame` đọc `4 byte header`, rồi dùng `readFully` đọc đúng số byte payload. Khi frame đầu hoàn tất, các byte tiếp theo thuộc frame thứ hai, dù TCP cung cấp dữ liệu thành 1 lần đọc hay nhiều lần đọc. Để gửi response, server chỉ cần đọc hết **hai frame theo hợp đồng demo**, không đợi phía client đóng output.

Những điểm cần nhớ:

1. Độ dài trong ví dụ đo bằng `payload.length` (**số byte UTF-8**), không phải `String.length()` (số code unit UTF-16). Chẳng hạn ký tự có dấu có thể cần nhiều byte UTF-8.
2. `DataInputStream.readFully(payload)` sẽ cố đọc đủ kích thước; nếu peer kết thúc stream trước khi đủ, nó ném `EOFException`. `readInt()` cũng có thể ném `EOFException` khi chưa nhận đủ 4 byte header.
3. Một giao thức thực phải quy định **byte order**, kích thước header, kiểu encoding, độ dài tối đa, phiên bản và cách ứng xử khi frame hỏng. Bên ngoài Java, server/client phải dùng đúng định dạng 4-byte big-endian này; không suy ra từ tên class `DataInputStream`.
4. `MAX_BYTES` giúp tránh kẻ gửi dữ liệu không tin cậy buộc server cấp phát bộ nhớ quá lớn. Ngoài giới hạn từng frame, hệ thống thực còn cần giới hạn tổng thời gian, số frame, rate và resource.
5. `DataInputStream.readUTF()/writeUTF()` dùng định dạng **modified UTF-8 của Java** và tiền tố độ dài riêng; không thay thế mặc nhiên cho protocol UTF-8 chuẩn dùng `getBytes(StandardCharsets.UTF_8)`.
6. Nếu peer mở connection nhưng gửi header rồi ngừng, `readFully` sẽ chờ; `setSoTimeout` giúp thoát thao tác đọc bị treo, song đó là **timeout**, không phải EOF thành công.

## 9. Đọc đến EOF hay đọc đủ message: chọn đúng hợp đồng

### 9.1. Những API có thể gây treo nếu peer không đóng

- `InputStream.readAllBytes()`: đọc tới EOF rồi trả mảng byte. Hữu ích với file hoặc một stream **được bảo đảm kết thúc**. Với TCP connection còn mở để tái sử dụng, gọi nó có thể chờ mãi, đồng thời gây vấn đề bộ nhớ nếu dữ liệu lớn.
- `InputStream.transferTo(output)`: chuyển liên tục tới EOF. Không tự phát hiện cuối một HTTP/WebSocket message, và không nên dùng vô hạn nếu không có lifecycle.
- `InputStream.readNBytes(n)`: cố đọc tối đa `n` byte, nhưng có thể trả ít hơn nếu EOF. Phải kiểm tra độ dài nếu protocol đòi **đúng n byte**.
- `DataInputStream.readFully(bytes)`: đọc đúng độ dài yêu cầu hoặc ném `EOFException` khi bị EOF quá sớm; vẫn có thể block/timeout nếu peer giữ kết nối mở mà không gửi đủ byte.
- `BufferedReader.readLine()`: chờ delimiter hoặc EOF. Nếu protocol không có newline và peer không đóng chiều gửi, kết quả có thể chờ.

### 9.2. Ví dụ deadlock phổ biến

Thiết kế sai khi **hai bên cùng chờ bên kia**:

```text
Client: write("REQUEST") -> read response (đợi)
Server: readAllBytes() -> tạo response (đợi EOF)
```

Client chưa gửi EOF vì còn muốn tái sử dụng output; server chưa tạo response vì `readAllBytes()` chưa nhìn thấy EOF. Kết quả: **cả hai cùng chờ**, không phải mạng tự ý “nuốt” byte. Có ba cách sửa tùy protocol:

1. Một request duy nhất: client viết payload, `flush()` và `shutdownOutput()`; server đọc đến EOF rồi trả response.
2. Dạng dòng: client viết `REQUEST\n` và `flush()`; server `readLine()` rồi xử lý, vẫn có thể tiếp tục nhận các dòng khác.
3. Dạng length prefix: client viết độ dài + payload; server đọc đủ độ dài, xử lý mà không đợi EOF.

Không sử dụng `sleep()` hoặc tăng buffer size để “sửa” deadlock protocol. Vấn đề nằm ở việc **thiếu quy tắc kết thúc message**.

## 10. Timeout, đóng tài nguyên và xử lý lỗi

### 10.1. Timeout cần áp dụng theo loại thao tác

```java
// Ví dụ minh họa trong một phương thức đã có Socket socket.
socket.connect(remoteEndpoint, 3000);
socket.setSoTimeout(5000);
```

`remoteEndpoint` phải là một `SocketAddress` hợp lệ được cung cấp từ ngoài; đây là **đoạn minh họa**, chưa phải chương trình độc lập.

- Tham số timeout của `connect(endpoint, milliseconds)` áp dụng khi cố thiết lập **kết nối TCP**. Nó không tự đặt timeout cho các lần đọc sau đó.
- `setSoTimeout(milliseconds)` áp dụng cho thao tác **đọc** trên input socket theo ngữ nghĩa SO_TIMEOUT. Sau khoảng chờ, có thể ném `SocketTimeoutException`; socket nhìn chung vẫn có thể dùng tiếp, nhưng ứng dụng phải quyết định có retry/đóng.
- `setSoTimeout(0)` nghĩa là timeout đọc **vô hạn**. Không nên để dữ liệu từ peer không tin cậy có thể giữ thread mãi mà không có chính sách timeout hợp lý.
- Timeout kết nối/đọc không thay thế cho giới hạn **tổng thời gian request**, giới hạn kích thước và cơ chế hủy tác vụ. `OutputStream.write` cũng có thể block do backpressure; không nên tự giả định `setSoTimeout` giới hạn thời gian ghi.

### 10.2. Đóng đúng đối tượng sở hữu socket

```java
try (Socket socket = new Socket()) {
    // Kết nối, sử dụng input/output trong phạm vi này.
}
// Socket tự được đóng, kể cả khi phát sinh exception.
```

Với stream lấy từ một socket, đóng `InputStream` hoặc `OutputStream` **cũng đóng socket tương ứng** theo hợp đồng Java `Socket`. Khi một chiều đã gửi xong nhưng vẫn cần đọc reply, hãy dùng `shutdownOutput()` hoặc framing ứng dụng. Đừng đóng stream riêng lẻ quá sớm.

Nếu thiết kế wrapper `BufferedReader`, `BufferedWriter`, `DataInputStream`, `DataOutputStream`, hãy xác định rõ **ai sở hữu việc đóng socket**. Khi mọi thao tác đã hoàn tất, `try-with-resources` trên socket là cách đơn giản và tin cậy cho ví dụ nhỏ.

**Phân biệt trạng thái:**

| Trạng thái | Dấu hiệu thường gặp | Hành động |
|---|---|---|
| Peer đã gửi EOF bình thường | `read == -1` hoặc `readLine == null` khi không còn ký tự | Kết thúc vòng lặp, kiểm tra message hoàn chỉnh |
| Đọc quá thời gian | `SocketTimeoutException` | Ghi rõ timeout; retry/đóng theo protocol |
| Kết nối bị reset | `SocketException` hoặc lỗi I/O cụ thể | Không xem như một response thành công |
| Thiếu byte theo length prefix | `EOFException` từ `readFully` | Từ chối frame chưa hoàn chỉnh |
| Client gửi payload vượt giới hạn | App kiểm tra kích thước và ném protocol error | Đóng hoặc từ chối theo chính sách |
| Ghi sau `shutdownOutput()` | `IOException`/`SocketException` | Không viết tiếp; tạo connection khác nếu cần |

**Đừng dựa vào `Socket.isClosed()` để đo peer đã đóng hay chưa.** Nó cho biết socket Java cục bộ có bị đóng, không phải cơ chế phát hiện EOF từ xa. Tương tự, `isInputShutdown()`/`isOutputShutdown()` phản ánh thao tác shutdown ở phía local, không thay cho đọc và parse protocol.

### 10.3. Trách nhiệm kiểm soát dữ liệu

Bất kỳ đoạn code nào đọc từ peer không tin cậy cũng nên có:

- **Giới hạn kích thước message**, kích thước frame, số lần đọc, số request/connection hoặc tổng byte phù hợp.
- **Giới hạn thời gian** đối với connect, đọc và xử lý; tránh một client giữ kết nối mãi mà không gửi đủ message.
- **Giao thức rõ ràng** về encoding, delimiter/length, thứ tự request-response và lúc nào được half-close/close.
- **Xử lý lỗi tách biệt**: EOF bình thường, EOF quá sớm, timeout, reset, parse failure và lỗi nghiệp vụ không bị gom thành “không có mạng”.
- **Đảm bảo xử lý đủ byte** khi viết giao thức riêng. Với `OutputStream` chuẩn, một lần `write(byte[])` thực hiện việc ghi mảng theo hợp đồng API; phía nhận **vẫn** cần vòng đọc theo framing, không dựa vào một lần read.
- **Không suy luận delivery từ `flush()`**. Để biết request được xử lý, protocol cần một response hoặc acknowledgement ở đúng tầng.

## 11. Tình huống kiểm tra hiểu bài

**Tình huống A — Byte `0` và EOF:** client gửi các byte `0x41 0x00 0x42`. `InputStream.read()` phía server có thể trả lần lượt 65, 0, 66, rồi chỉ trả `-1` **sau khi phía gửi kết thúc chiều output** và server đọc hết dữ liệu. Không được xem `0` là EOF.

**Tình huống B — Đọc ít hơn buffer:** client `write` 1.000 byte; server cấp buffer 4.096 byte và lần đọc đầu nhận 400 byte. Đã hết message chưa? **Chưa thể kết luận.** Còn ít nhất 600 byte của lần ghi đó có thể đến sau, và protocol có thể còn message khác.

**Tình huống C — Timeout:** server `read()` chờ 5 giây rồi ném `SocketTimeoutException`. Có phải client đã gửi FIN? **Không.** Đó chỉ là chờ quá lâu; EOF sạch được biểu diễn bằng `-1`.

**Tình huống D — Client vẫn muốn đọc response:** client ghi một payload mà protocol xác định kết thúc bằng EOF; server chỉ xử lý khi thấy EOF. Client nên làm gì sau `flush()`? **Gọi `shutdownOutput()`**, giữ chiều input để nhận reply; đừng `close()` toàn bộ socket trước khi đọc reply.

**Tình huống E — Nhiều message:** client gửi `"A"` rồi `"B"` trong hai lần `write`, server đọc một lần nhận `"AB"`. Có lỗi TCP? **Không.** TCP có thể gộp dữ liệu ở các lần đọc; cần delimiter hoặc length prefix để phân biệt hai message.

**Tình huống F — `readLine()` trả gì?** Với dữ liệu `"HELLO\n\n"`, hai lần `readLine()` đầu trả `"HELLO"` và `""`; nếu sau đó peer đóng chiều gửi, lần kế tiếp mới trả `null`. **Dòng trống không phải EOF.**

**Tình huống G — Header là 10 nhưng peer chỉ gửi 6 byte rồi FIN:** `DataInputStream.readFully(new byte[10])` phải đọc đủ hay báo `EOFException`? Nó ném **`EOFException`**, vì frame không hoàn chỉnh. Không xử lý 6 byte như message hợp lệ nếu protocol yêu cầu 10.

**Tình huống H — Sau `shutdownOutput()` có thể nhận reply không?** Có. Half-close chỉ kết thúc **chiều gửi** của socket; chiều nhận còn sử dụng được cho đến khi peer kết thúc hoặc xảy ra lỗi.

## 12. Tóm tắt vận dụng

- `Socket.getInputStream()` đọc byte từ peer; `Socket.getOutputStream()` ghi byte sang peer. TCP bảo đảm **thứ tự byte**, không có ranh giới message do lần gọi `write()` tạo ra.
- `read() == -1` là **EOF**, `read() == 0` có thể là dữ liệu byte bằng 0 (với overload đọc một byte). Chờ, timeout và reset **không đồng nghĩa** với EOF.
- `flush()` đẩy Java buffer xuống stream; không phải dấu kết thúc message, không phải peer ACK ở tầng ứng dụng.
- `shutdownOutput()` kết thúc chiều gửi nhưng vẫn cho phép đọc response; `close()` kết thúc việc sử dụng socket. Không đóng output stream sớm khi vẫn cần nhận reply.
- Khi **EOF là delimiter**, đọc tới `-1`; khi có **nhiều message trên một connection**, dùng newline, length prefix hoặc parser chuẩn; luôn có timeout, giới hạn kích thước và quy tắc xử lý lỗi.
- Để debug một kết nối “bị treo”, hỏi: **bên đọc đang chờ byte, delimiter, số byte còn thiếu hay EOF? Bên gửi đã `flush()` và có thực sự phát tín hiệu kết thúc tương ứng chưa?**

### Tài liệu Java 17 để tra cứu

- [`InputStream`: `read`, `readNBytes`, `readAllBytes`, `transferTo`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [`OutputStream`: `write`, `flush`, `close`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html)
- [`Socket`: `getInputStream`, `getOutputStream`, `shutdownInput`, `shutdownOutput`, `setSoTimeout`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [`BufferedReader` và `BufferedWriter`: `readLine`, `newLine`, `flush`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html)
- [`DataInputStream` và `DataOutputStream`: `readFully`, `readInt`, `writeInt`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html)
