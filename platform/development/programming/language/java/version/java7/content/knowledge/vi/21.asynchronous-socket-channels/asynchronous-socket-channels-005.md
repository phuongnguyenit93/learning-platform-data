# Java 7 — Kênh mạng bất đồng bộ: Đọc ghi một phần, kết thúc luồng và lỗi kết nối

## 1. Mục tiêu, bối cảnh và kết luận cốt lõi

`AsynchronousSocketChannel` và `AsynchronousServerSocketChannel` thuộc Java NIO.2, được giới thiệu từ **Java 7** và vẫn là API hiện hành trên Java 17+. Chúng cho phép khởi tạo thao tác kết nối, chấp nhận kết nối, đọc hoặc ghi dữ liệu qua socket bất đồng bộ bằng `Future` hoặc `CompletionHandler`.

Trong một kết nối TCP:

- **Một lần `write` không đồng nghĩa toàn bộ buffer đã được ghi.**
- **Một lần `read` không đồng nghĩa đã nhận đủ một thông điệp.**
- TCP truyền **dòng byte có thứ tự**, không tự giữ ranh giới giữa các lời gọi `write` của ứng dụng.
- `read` trả **`-1` khi nhận kết thúc luồng đầu vào (EOF)**, không phải mọi trường hợp lỗi kết nối.
- `shutdownOutput()` chỉ đóng **chiều ghi** và thường khiến bên kia cuối cùng đọc `-1` sau khi đã tiêu thụ hết dữ liệu chờ; chiều đọc của socket vẫn có thể hoạt động.
- `close()` đóng channel; các pending operations có thể thất bại.
- Một socket bất đồng bộ chỉ hỗ trợ **tối đa một lượt đọc và một lượt ghi đang chờ** tại cùng thời điểm. Một lượt đọc thứ hai khi lượt đọc trước chưa xong gây `ReadPendingException`; tương tự `WritePendingException` cho ghi.
- Khi operation hoàn tất, nhận **số byte thực tế `n`** và cập nhật trạng thái buffer/protocol; không tự suy rằng đã đủ dữ liệu hoặc peer đã xử lý thông điệp.
- Timeout của chính asynchronous socket operation có ngữ nghĩa **khác** timeout của `Future.get(...)`. Sau socket-operation timeout, buffer có thể rơi vào trạng thái không xác định; không tùy tiện tái dùng.

Sau bài này bạn có thể xây dựng read/write loops an toàn với partial results, một protocol length-prefixed, xử lý EOF/half-close, phân biệt các lỗi network, điều phối callbacks và test bằng loopback mà không giả định packet boundaries.

**Phạm vi:** Bài tập trung đúng vào “Đọc ghi một phần, kết thúc luồng và lỗi kết nối” trong chủ đề cha “Kênh mạng bất đồng bộ”. Những API vẫn có giá trị hiện nay được ưu tiên; chương trình biên dịch với `javac --release 17`. Các tiện ích có từ sau Java 7 được ghi rõ, không coi Java 7 là kiến trúc lỗi thời.

## 2. Phân biệt kênh mạng với kênh tệp bất đồng bộ

| Khía cạnh | `AsynchronousSocketChannel` | `AsynchronousFileChannel` |
| --- | --- | --- |
| Dữ liệu | Luồng byte hai chiều qua một kết nối mạng | Bytes tại vị trí trong file |
| `read` | `read(ByteBuffer)`, có overload callback/timeout | `read(ByteBuffer,long filePosition)` |
| `write` | `write(ByteBuffer)`, có overload callback/timeout | `write(ByteBuffer,long filePosition)` |
| Offset file | **Không có tham số filePosition**; TCP tự vận chuyển bytes theo luồng | **Có offset kiểu long** mỗi operation |
| Kết thúc input | Remote đóng chiều ghi/đóng kết nối đúng cách có thể làm read trả `-1` | Đọc tới end-of-file trả `-1` |
| Vị trí bytes | Theo thứ tự byte stream của TCP | Theo offsets được ứng dụng chỉ định |
| Một lượt read | Có thể nhận ít bytes hơn buffer.remaining() | Cũng có thể đọc ít hơn |
| Một lượt write | Có thể ghi ít hơn buffer.remaining() | Cũng có thể ghi ít hơn |
| Concurrent operations | Một read + một write outstanding trên cùng socket | Có thể có nhiều positional I/Os outstanding với buffers riêng |
| Lifecycle | connect, read/write, half-close, close | open, read/write, close |

**Không áp dụng quy tắc `fileOffset += n` của kênh tệp vào TCP socket.** Với `AsynchronousSocketChannel`, caller không truyền file offset; việc ứng dụng cần theo dõi là tiến độ trong `ByteBuffer`, số bytes của frame/protocol và trạng thái kết nối.

TCP không đảm bảo rằng hai lời gọi `write("ABC")` và `write("DEF")` sẽ ứng với hai lần `read` riêng. Consumer có thể nhận `ABCDEF` trong một lần đọc, hoặc `A`, `BC`, `D`, `EF` qua nhiều lần đọc. **Ranh giới của network packet và ranh giới của lời gọi I/O không phải ranh giới message của ứng dụng.**

## 3. Các đối tượng và vòng đời kết nối

Các lớp chính:

- `AsynchronousServerSocketChannel`: socket server có thể `bind` rồi `accept` bất đồng bộ.
- `AsynchronousSocketChannel`: socket client được `open` rồi `connect`; socket phía server thu được từ `accept` cũng là `AsynchronousSocketChannel`.
- `ByteBuffer`: vùng bytes mà mỗi read/write operation sử dụng.
- `Future<Integer>` hoặc `CompletionHandler<Integer,A>`: cách nhận số byte chuyển trong read/write.
- `Future<Void>` hoặc `CompletionHandler<Void,A>`: kết quả connect.
- `Future<AsynchronousSocketChannel>` hoặc handler tương ứng: kết quả accept.
- `AsynchronousChannelGroup`: nhóm channels dùng chung tài nguyên xử lý hoàn tất I/O, có thể cấu hình executor trong chương trình lớn.

Luồng thường gặp:

```text
SERVER                                   CLIENT
open AsynchronousServerSocketChannel    open AsynchronousSocketChannel
    |                                        |
bind(loopback, ephemeral port)          connect(serverAddress)
    |                                        |
accept() → Future<SocketChannel>              |
    |                                 connect Future completes
acceptedSocket                                   |
    |<------------ TCP byte stream ------------->|
read(dst)  <------------------------- write(src)
write(src) -------------------------> read(dst)
    |                                        |
read() eventually -1   <------------- shutdownOutput()
write(response) ---------------------> read(response)
shutdownOutput() --------------------> read() eventually -1
    |                                        |
close()                                  close()
```

### 3.1. Server phải bind trước accept

Một `AsynchronousServerSocketChannel` vừa `open` thì chưa tự bind. Gọi `accept()` trước `bind(...)` có thể ném `NotYetBoundException`.

### 3.2. Client phải connect trước I/O

Một `AsynchronousSocketChannel` vừa `open()` là **open nhưng chưa connected**. `read` hoặc `write` trước khi `connect` thành công sẽ ném `NotYetConnectedException`. `getRemoteAddress()` có thể trả null khi chưa connected.

### 3.3. Một connection không phải nhiều connections

Sau khi socket đã connected, không gọi `connect` thêm lần nữa trên chính channel ấy. Điều này có thể gây `AlreadyConnectedException`. Với reconnect, cần tạo **channel mới** và khởi tạo state/protocol mới; channel gặp connect failure thường đã bị đóng theo hợp đồng Java.

### 3.4. Thao tác bất đồng bộ ≠ không có thread nào chờ

`read`, `write`, `connect`, `accept` khởi tạo operation bất đồng bộ và trả ngay một future/đăng ký callback. Nếu chính thread gọi `future.get()`, thread ấy có thể block tới khi hoàn tất. Sử dụng `CompletionHandler` để xử lý theo event có thể tránh kiểu chờ tuần tự, nhưng cần concurrency/backpressure/lifecycle đúng.

## 4. ByteBuffer và số byte được chuyển

`ByteBuffer` có ba giá trị cốt lõi:

```text
0 <= position <= limit <= capacity
remaining() = limit - position
```

Đối với một `read(dst)`:

- `dst` phải là buffer **có thể ghi**.
- Operation có thể chuyển tối đa `dst.remaining()` bytes.
- Nếu chuyển `n>0` bytes, `dst.position()` được tăng tương ứng.
- `dst.limit()` không tự thay đổi.
- Sau khi read hoàn tất, gọi `dst.flip()` để chuyển sang lấy bytes từ buffer.
- Nếu không nhận đủ frame, có thể giữ buffer và gọi read tiếp **không clear** để điền nốt.

Đối với `write(src)`:

- `src` là buffer **để đọc bytes từ nó**.
- Operation có thể chuyển tối đa `src.remaining()` bytes.
- Nếu ghi `n>0`, `src.position()` tăng tương ứng.
- Nếu `src.hasRemaining()` còn true, phải **khởi tạo write tiếp** khi protocol cần gửi hết.
- Không `clear` buffer còn bytes chưa ghi hoặc vẫn đang được operation pending sử dụng.

### 4.1. `flip`, `clear`, `compact`

| Method | Công dụng | Dùng đúng |
| --- | --- | --- |
| `flip()` | `limit=old position`, `position=0` | Sau khi nạp dữ liệu vào buffer, chuẩn bị tiêu thụ |
| `clear()` | `position=0`, `limit=capacity` | Chỉ sau khi toàn bộ dữ liệu cũ đã tiêu thụ |
| `compact()` | Dồn phần chưa tiêu thụ về đầu, chuẩn bị nạp thêm | Khi decoder/parser vẫn cần bytes còn lại |
| `hasRemaining()` | Xác minh buffer còn bytes chưa tiêu thụ/ghi | Điều kiện lặp writeFully/readFully |
| `remaining()` | Số bytes trong vùng hợp lệ hiện tại | Giới hạn của một operation |

`clear()` **không xóa vật lý bytes**. `ByteBuffer.wrap(byte[])` đã sẵn để đọc các bytes của mảng; **không flip vô điều kiện** trên buffer vừa wrap chưa put.

### 4.2. Buffer đang pending I/O không được sửa

Các ByteBuffers không an toàn để nhiều threads/operations concurrent cùng sử dụng. Từ lúc gọi `read/write` tới khi I/O **thực sự hoàn tất**, không tự chuyển position/limit, ghi thêm, clear hoặc trả buffer về pool.

`Future.get(timeout)` timeout chỉ có nghĩa **người chờ chưa thấy kết quả trong khoảng thời gian ấy**, chứ không bảo đảm I/O đã bị hủy. Với timeout được truyền **trực tiếp vào `AsynchronousSocketChannel.read/write`**, Java còn cảnh báo **buffer state có thể undefined** khi timeout; hãy chủ động ngừng sử dụng/đóng connection theo recovery policy.

## 5. Kết quả read/write: `n>0`, `n==0` và `n==-1`

### 5.1. Read

| Kết quả read | Nghĩa | Hành động |
| --- | --- | --- |
| `n>0` | Đã nhận `n` bytes từ TCP stream | Xử lý bytes, tiếp tục đọc nếu frame chưa hoàn chỉnh |
| `n==0` | Không có byte tiến triển, ví dụ `dst.remaining()==0` | Không coi là EOF; đánh giá buffer/progress |
| `n==-1` | Kết thúc luồng đầu vào (EOF) | Kết thúc protocol EOF-delimited, hoặc báo truncated nếu frame còn thiếu |
| Exception | I/O/connect/timeout/close/OS failure | Phân loại lỗi, không giả lập EOF |

`-1` là **EOF** của đọc, không phải “lỗi mạng” tự động. Nếu peer đã gửi đủ dữ liệu rồi half-close chiều ghi, EOF là một cách báo kết thúc hợp lệ của protocol.

### 5.2. Write

| Kết quả write | Nghĩa | Hành động |
| --- | --- | --- |
| `n>0` | `n` bytes đã được chấp nhận/ghi bởi operation | Tiếp tục với bytes còn lại nếu cần |
| `n==0` | Chưa chuyển byte | Xử lý không tiến triển; tránh hot loop |
| `n<0` | Không phải giá trị EOF bình thường cho write | Treat as abnormal failure |
| Exception | Kết nối lỗi/đã đóng/hết thời gian | Báo thất bại; xác minh có phần dữ liệu nào đã được gửi |

**Write completion ≠ remote application đã đọc/parse/commit dữ liệu.** Nó chỉ nói operation đã hoàn tất theo tầng socket. Nếu nghiệp vụ cần xác nhận remote xử lý, hãy định nghĩa response/ACK có semantics rõ ở tầng protocol/application.

### 5.3. Buffer không có remaining

Nếu `remaining()==0`, `read`/`write` hoàn tất ngay với `0` mà không thực hiện I/O theo `AsynchronousByteChannel`. Không dùng `0` làm dấu hiệu connection đã đóng.

### 5.4. Không biến bytes thành String tùy tiện

TCP là byte stream. Một ký tự UTF-8 có thể bị chia qua nhiều lần read. Không decode riêng từng chunk bằng `new String(chunk,UTF_8)` nếu chunk có thể kết thúc giữa ký tự. Dùng `CharsetDecoder` stateful hoặc gom bytes đủ frame rồi decode một lần khi payload nhỏ/có giới hạn.

## 6. Hai helper có thể tái sử dụng: writeAll và readExactly

### 6.1. Ghi hết bytes trong source ByteBuffer

```java
static int writeAll(AsynchronousSocketChannel ch, ByteBuffer src)
        throws Exception {
    int total = 0;
    int zeros = 0;
    while (src.hasRemaining()) {
        int n = ch.write(src).get(5, TimeUnit.SECONDS);
        if (n < 0) throw new IOException("Unexpected negative write");
        if (n == 0) {
            if (++zeros > 16) throw new IOException("Write stalled");
            continue;
        }
        zeros = 0;
        total += n;
    }
    return total;
}
```

Đây là helper **không phải standalone class**; cần import `IOException`, `AsynchronousSocketChannel`, `ByteBuffer`, `TimeUnit` và caller quản lý connection/lifetime.

Mỗi `write` trả số bytes thực tế. Buffer position tự tiến. Helper lặp tới khi `hasRemaining()==false`. Guard 16 lần là **chính sách demo để tránh lặp mãi**, không phải threshold bắt buộc của Java.

**Không trộn helper này với byte offset trên file**: network socket tự tiến dòng TCP, nên `write(ByteBuffer)` không nhận `long filePosition`.

### 6.2. Đọc đủ N bytes của protocol

```java
static void readExactly(AsynchronousSocketChannel ch, ByteBuffer dst)
        throws Exception {
    int zeros = 0;
    while (dst.hasRemaining()) {
        int n = ch.read(dst).get(5, TimeUnit.SECONDS);
        if (n == -1) throw new EOFException("Truncated frame");
        if (n == 0) {
            if (++zeros > 16) throw new IOException("Read stalled");
            continue;
        }
        zeros = 0;
    }
}
```

Đây là helper minh họa. Nó chỉ báo đủ khi buffer đã được nạp hết **vùng remaining lúc gọi**. Nếu EOF tới trước, báo `EOFException` vì protocol cần đúng N bytes.

**Không clear `dst` giữa các lần read trong cùng helper**: làm thế sẽ bỏ phần đã nhận và có thể chờ sai số bytes.

### 6.3. Một giới hạn quan trọng của helper

`get(5,SECONDS)` chờ tối đa 5 giây **mỗi operation**; nếu timeout, operation có thể vẫn pending, trong khi code stack đang unwind. Production phải quản lý cancellation/close/buffer ownership và deadline tổng. Code đơn giản được dùng để làm rõ **đếm bytes**; không nên coi đó là production network stack hoàn chỉnh.

## 7. Chương trình A — Kết nối loopback và trao đổi PING/PONG

Chương trình này chạy cả listener và client trong một JVM, kết nối qua loopback/port hệ điều hành chọn. Nó không cần server ngoài. Hai chiều sử dụng `writeAll` và `readExactly`, nên không phụ thuộc provider tự chia packet ra sao.

Lưu **`LoopbackRoundTripDemo.java`**:

```java
import java.io.*;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public final class LoopbackRoundTripDemo {
    static int writeAll(AsynchronousSocketChannel ch, ByteBuffer buf)
            throws Exception {
        int total = 0, zeros = 0;
        while (buf.hasRemaining()) {
            int n = ch.write(buf).get(5, TimeUnit.SECONDS);
            if (n < 0) throw new IOException("Unexpected negative write");
            if (n == 0) {
                if (++zeros > 16) throw new IOException("Write stalled");
                continue;
            }
            zeros = 0;
            total += n;
        }
        return total;
    }

    static String readExactly(AsynchronousSocketChannel ch, int bytes)
            throws Exception {
        ByteBuffer b = ByteBuffer.allocate(bytes);
        int zeros = 0;
        while (b.hasRemaining()) {
            int n = ch.read(b).get(5, TimeUnit.SECONDS);
            if (n == -1)
                throw new EOFException("Truncated: " + b.position());
            if (n == 0) {
                if (++zeros > 16) throw new IOException("Read stalled");
                continue;
            }
            zeros = 0;
        }
        b.flip();
        byte[] all = new byte[b.remaining()];
        b.get(all);
        return new String(all, StandardCharsets.US_ASCII);
    }

    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open();
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {

            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));

            Future<AsynchronousSocketChannel> incoming =
                    listener.accept();
            client.connect(
                    (InetSocketAddress) listener.getLocalAddress())
                    .get(5, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel server =
                         incoming.get(5, TimeUnit.SECONDS)) {
                int count = writeAll(client, ByteBuffer.wrap(
                        "PING".getBytes(StandardCharsets.US_ASCII)));
                String req = readExactly(server, 4);

                writeAll(server, ByteBuffer.wrap(
                        "PONG".getBytes(StandardCharsets.US_ASCII)));
                String resp = readExactly(client, 4);

                System.out.println("clientConnected=" +
                        (client.getRemoteAddress() != null));
                System.out.println("bytesSent=" + count);
                System.out.println("serverReceived=" + req);
                System.out.println("clientReceived=" + resp);
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 LoopbackRoundTripDemo.java
java LoopbackRoundTripDemo
```

**Stdout đã kiểm chứng trên JDK/Windows loopback:**

```text
clientConnected=true
bytesSent=4
serverReceived=PING
clientReceived=PONG
```

Giải thích:

1. `bind(loopback,0)` yêu cầu hệ điều hành chọn một port trống.
2. `accept()` khởi tạo một pending accept, trả `Future<AsynchronousSocketChannel>`.
3. Client gọi `connect(...)`, đợi future hoàn tất.
4. `incoming.get()` trả **socket server cho connection cụ thể**, không phải listener ban đầu.
5. Client gửi đủ 4 byte `PING`; server đọc đúng 4 byte.
6. Server gửi đủ 4 byte `PONG`; client đọc đúng 4 byte.
7. Listener, client và accepted socket được đóng bằng try-with-resources.

Vì dùng loopback, chương trình tránh sự bất định của DNS/Internet; nhưng môi trường sandbox/firewall hạn chế socket có thể không cho bind/connect. Thành công trên máy thử không là bảo đảm cho mọi network.

## 8. TCP là byte stream: không có message boundaries

Giả sử sender gọi:

```java
writeAll(channel, ByteBuffer.wrap(new byte[] {65, 66, 67}));
writeAll(channel, ByteBuffer.wrap(new byte[] {68, 69, 70}));
```

Đây là mảnh minh họa. Nó biểu diễn gửi bytes `ABC` rồi `DEF`. Receiver **không được giả định** sẽ thấy đúng hai lần read trả `ABC` và `DEF`. Một vài khả năng hoàn toàn hợp lệ:

```text
read #1 -> ABCDEF
read #1 -> A
read #2 -> BCD
read #3 -> EF
read #1 -> ABC
read #2 -> DEF
```

Ngay cả khi `writeAll` bảo đảm phía sender đã giao hết bytes cho tầng socket, điều đó **không thêm ký hiệu ngăn cách thông điệp** vào dòng TCP.

### 8.1. Ba cách framing phổ biến

1. **Fixed-length frames:** Bản ghi có độ dài cố định N bytes; receiver đọc chính xác N.
2. **Length-prefix:** Gửi header ghi độ dài payload, sau đó đúng số bytes ấy; receiver kiểm tra giới hạn trước khi allocate.
3. **Delimiter:** Ví dụ newline cho text line protocol; parser phải giữ trạng thái khi delimiter nằm ở ranh giới các chunks, và xử lý escaping/encoding.

Một protocol khác có thể dùng EOF (half-close) để báo hết request, nhưng như vậy connection thường không thể nhận thêm requests theo chiều đó. Chọn framing dựa trên requirement, không dựa vào kích thước packet.

### 8.2. Length-prefix cần bảo mật

Một header `int length` từ bên kia là dữ liệu **không tin cậy**. Kiểm:

- Length không âm.
- Length ≤ kích thước message tối đa mà application cho phép.
- Tổng lượng bytes nhận, CPU, memory và thời gian đều có giới hạn.
- EOF trước khi đủ body phải bị báo là truncated frame.
- Decode text sau khi có đủ bytes, không theo từng chunk tùy tiện.

## 9. Chương trình B — Frame có độ dài và UTF-8 qua buffer 3 byte

Lưu **`LengthFrameDemo.java`**. Gửi header 4 byte big-endian chứa payload length, rồi payload `hi🙂!` dài 7 byte UTF-8. Receiver đọc header 4 byte, sau đó body qua buffer capacity 3, để chứng minh không dựa vào ranh giới ký tự Unicode hoặc TCP packet.

```java
import java.io.*;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public final class LengthFrameDemo {
    static int writeAll(AsynchronousSocketChannel ch, ByteBuffer b)
            throws Exception {
        int total = 0, zeros = 0;
        while (b.hasRemaining()) {
            int n = ch.write(b).get(5, TimeUnit.SECONDS);
            if (n < 0) throw new EOFException("Negative write");
            if (n == 0) {
                if (++zeros > 16) throw new IOException("Stalled write");
                continue;
            }
            total += n;
            zeros = 0;
        }
        return total;
    }

    static void readAll(AsynchronousSocketChannel ch, ByteBuffer b)
            throws Exception {
        int zeros = 0;
        while (b.hasRemaining()) {
            int n = ch.read(b).get(5, TimeUnit.SECONDS);
            if (n == -1) throw new EOFException("Truncated frame");
            if (n == 0) {
                if (++zeros > 16) throw new IOException("Stalled read");
                continue;
            }
            zeros = 0;
        }
    }

    public static void main(String[] args) throws Exception {
        String content = "hi\uD83D\uDE42!";
        byte[] payload = content.getBytes(StandardCharsets.UTF_8);

        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open();
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            Future<AsynchronousSocketChannel> accepted = listener.accept();
            client.connect((InetSocketAddress) listener.getLocalAddress())
                    .get(5, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel server =
                         accepted.get(5, TimeUnit.SECONDS)) {
                ByteBuffer header = ByteBuffer.allocate(4);
                header.putInt(payload.length);
                header.flip();

                writeAll(client, header);
                writeAll(client, ByteBuffer.wrap(payload));

                ByteBuffer gotHeader = ByteBuffer.allocate(4);
                readAll(server, gotHeader);
                gotHeader.flip();
                int size = gotHeader.getInt();
                if (size < 0 || size > 1024)
                    throw new IOException("Invalid frame size");

                ByteArrayOutputStream body = new ByteArrayOutputStream();
                ByteBuffer chunk = ByteBuffer.allocate(3);
                int chunks = 0;
                while (body.size() < size) {
                    chunk.clear();
                    chunk.limit(Math.min(
                            chunk.capacity(), size - body.size()));
                    readAll(server, chunk);
                    chunk.flip();
                    chunks++;
                    byte[] part = new byte[chunk.remaining()];
                    chunk.get(part);
                    body.write(part);
                }

                System.out.println("frameLength=" + size);
                System.out.println("bodyBytes=" + body.size());
                System.out.println("chunksAtLeast3=" + (chunks >= 3));
                System.out.println("roundTrip=" + content.equals(
                    new String(body.toByteArray(),
                            StandardCharsets.UTF_8)));
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 LengthFrameDemo.java
java LengthFrameDemo
```

**Stdout đã kiểm chứng:**

```text
frameLength=7
bodyBytes=7
chunksAtLeast3=true
roundTrip=true
```

### 9.1. Phân tích vì sao ví dụ không mất bytes

- `ByteBuffer.putInt` ghi length thành 4 byte. `flip` header trước write.
- `writeAll` ghi hết header trước payload theo thứ tự byte stream.
- `readAll` đọc đúng 4 byte header ngay cả khi một read chỉ trả ít.
- `gotHeader.getInt()` lấy length theo big-endian mặc định của ByteBuffer; protocol cần định nghĩa thứ tự byte rõ.
- `if(size<0||size>1024)` chặn không cấp phát payload tùy ý theo input.
- Body được đọc bằng buffer capacity 3; ít nhất ba **application chunks** là cần thiết cho 7 byte.
- Chỉ sau khi thu đúng bảy byte mới decode UTF-8 một lần, tránh cắt emoji giữa các lần decode.

**Quan trọng:** `chunksAtLeast3=true` phát sinh vì code chủ động dùng buffer 3 byte, **không chứng minh OS đã chia TCP thành đúng ba packets hoặc ba reads**. Một chunk của chương trình có thể cần một hoặc nhiều `read` nếu provider trả partial result.

### 9.2. Không gom toàn bộ thông điệp khổng lồ vào RAM

`ByteArrayOutputStream` ở đây phù hợp payload có giới hạn 1024 byte. Với message lớn, dùng bounded streaming parser/storage; cấp quota theo user, kết nối và hệ thống.

## 10. Kết thúc luồng: EOF là gì?

`AsynchronousSocketChannel.read` trả `-1` khi đã tới **end-of-stream của chiều đọc**. Trong TCP, một trường hợp hợp lệ là peer đã **shutdown output** hoặc đóng connection một cách có trật tự và mọi bytes trước đó đã được tiêu thụ.

Vì TCP có **hai chiều**, đóng chiều gửi của A không tự động đóng chiều nhận phản hồi của A:

```text
CLIENT                                     SERVER
write("cat")  --------------------------> read "cat"
shutdownOutput() ---- FIN (orderly) ----> read() eventually -1
read response <------------------------- write("ACK")
read() eventually -1 <-- shutdownOutput() 
```

### 10.1. EOF không đồng nghĩa network failure

- Một protocol cố ý dùng EOF để đánh dấu cuối request: EOF đúng lúc là **thành công**.
- Một protocol cần nhận đúng 20 bytes body nhưng read trả `-1` sau 11 bytes: **truncated message**, phải báo lỗi.
- Một socket chưa connected: thường ném `NotYetConnectedException`, không trả `-1`.
- Một connection reset/đứt bất thường: có thể báo `IOException`; không phải tất cả lỗi đều được biến thành EOF.

### 10.2. EOF chỉ nói peer sẽ không gửi thêm bytes theo chiều ấy

`-1` không xác nhận peer đã xử lý/commit dữ liệu ứng dụng. Nếu protocol yêu cầu xác nhận kết quả, phải có ACK/response với semantics rõ, thường trước khi hướng gửi response của peer kết thúc.

## 11. Half-close: shutdownOutput, shutdownInput và close

Ba thao tác khác nhau:

| Operation | Chiều tác động | Hành vi |
| --- | --- | --- |
| `shutdownOutput()` | Ghi ra peer | Không gửi thêm bytes; peer có thể đọc dữ liệu cũ rồi thấy EOF; chiều read của local socket vẫn dùng được |
| `shutdownInput()` | Đọc từ peer | Read tiếp theo trả -1; tác động lên bytes chưa đọc/pending read có khía cạnh provider/OS-dependent |
| `close()` | Channel cả hai chiều | Đóng resource; pending operations có thể thất bại, không hứa remote nhận hết bytes |
| Peer `shutdownOutput()` | Chiều read của local | Sau bytes còn chờ, read thường trả -1 |
| Peer reset/error | Kết nối bất thường | Read/write có thể thất bại với `IOException`, không có đảm bảo một mã lỗi duy nhất |

Theo API Java 17, sau `shutdownOutput()`, những lời gọi write tiếp theo thất bại với `ClosedChannelException`. Với overload trả Future, lỗi có thể hiện qua `ExecutionException.getCause()`.

**Không gọi `shutdownOutput` khi buffer còn bytes chưa gửi.** Trước hết bảo đảm `writeAll` đã hoàn tất hoặc xử lý failure; cần protocol ACK nếu muốn biết bên kia đã thực sự nhận/xử lý.

### 11.1. Khi nào half-close hợp lý?

Ví dụ request stream có độ dài không biết trước, client gửi cho tới EOF rồi chờ server response. Đây là một protocol được thỏa thuận:

1. Client gửi đủ body.
2. Client `shutdownOutput` báo end-of-request.
3. Server đọc đến `-1`, xử lý và gửi response.
4. Server `shutdownOutput` nếu response cũng EOF-delimited.
5. Client đọc response đến `-1` rồi hai bên close.

Nếu cần nhiều requests trên cùng connection, half-close ở request đầu sẽ cấm client gửi requests kế tiếp; nên dùng framing length-prefix hoặc delimiter thay vì EOF-delimited request.

## 12. Chương trình C — HalfCloseDemo.java

```java
import java.io.*;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public final class HalfCloseDemo {
    static void send(AsynchronousSocketChannel ch, String s)
            throws Exception {
        ByteBuffer b = ByteBuffer.wrap(
                s.getBytes(StandardCharsets.US_ASCII));
        int zeros = 0;
        while (b.hasRemaining()) {
            int n = ch.write(b).get(5, TimeUnit.SECONDS);
            if (n <= 0) {
                if (++zeros > 16) throw new IOException("No progress");
                continue;
            }
            zeros = 0;
        }
    }

    static String drain(AsynchronousSocketChannel ch)
            throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        ByteBuffer b = ByteBuffer.allocate(2);
        int zeros = 0;
        while (true) {
            b.clear();
            int n = ch.read(b).get(5, TimeUnit.SECONDS);
            if (n == -1) break;
            if (n == 0) {
                if (++zeros > 16) throw new IOException("No progress");
                continue;
            }
            zeros = 0;
            b.flip();
            byte[] x = new byte[b.remaining()];
            b.get(x);
            out.write(x);
        }
        return new String(
                out.toByteArray(), StandardCharsets.US_ASCII);
    }

    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open();
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            Future<AsynchronousSocketChannel> incoming = listener.accept();
            client.connect((InetSocketAddress) listener.getLocalAddress())
                    .get(5, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel server =
                         incoming.get(5, TimeUnit.SECONDS)) {
                send(client, "cat");
                client.shutdownOutput();

                System.out.println("serverData=" + drain(server));
                send(server, "ACK");
                server.shutdownOutput();

                System.out.println("clientData=" + drain(client));
                System.out.println("clientOpenAfterHalfClose=" +
                        client.isOpen());
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 HalfCloseDemo.java
java HalfCloseDemo
```

**Stdout đã kiểm chứng:**

```text
serverData=cat
clientData=ACK
clientOpenAfterHalfClose=true
```

Giải thích:

- Client gửi `cat`, sau đó đóng **chiều ghi**.
- Server đọc bằng buffer capacity 2 cho đến `-1`, ghép đúng `cat`.
- Server vẫn gửi `ACK` qua chiều ngược; client vẫn đọc được.
- Server cũng shutdown output; client drain đến EOF.
- `client.isOpen()` vẫn true trước khi kết thúc try block, dù output đã shutdown.
- Try-with-resources cuối cùng mới đóng socket và listener.

**Cảnh báo:** Đây là một request-response đơn giản dựa trên EOF. Nếu peer không half-close theo protocol, `drain` có thể chờ; các `get` trong demo giúp không bị chờ vô hạn nhưng timeout vẫn cần cancellation/lifecycle policy ở production.

## 13. Bắt lỗi kết nối: phân loại theo giai đoạn

Lỗi network cần được phân biệt theo giai đoạn:

| Giai đoạn | Tình huống | API/exception đáng chú ý |
| --- | --- | --- |
| Trước bind | Gọi `accept` trên listener chưa bind | `NotYetBoundException` |
| Accept đang pending | Gọi `accept` lần hai trên cùng listener | `AcceptPendingException` |
| Trước connect | Gọi read/write socket client chưa connected | `NotYetConnectedException` |
| Connect remote unresolved | SocketAddress chưa được resolve | `UnresolvedAddressException` |
| Connect đã thành công | Gọi connect lần nữa | `AlreadyConnectedException` |
| Connect đang pending | Gọi connect lần nữa | `ConnectionPendingException` |
| Kết nối bị từ chối/mất route | Connect operation thất bại | Thường `IOException` ở callback hoặc `ExecutionException.getCause()`, cụ thể tùy OS/provider |
| Read pending | Một read thứ hai chưa đợi read trước | `ReadPendingException` |
| Write pending | Một write thứ hai chưa đợi write trước | `WritePendingException` |
| Read/write channel đóng | Operation có thể bị reject/fail | `ClosedChannelException`, `AsynchronousCloseException` |
| Read after remote orderly FIN | Đọc hết bytes còn lại rồi EOF | `-1` (không nhất thiết exception) |
| Write sau local `shutdownOutput` | Local không còn quyền gửi | `ClosedChannelException` |
| Timed socket I/O hết hạn | Operation kết thúc do timeout | `InterruptedByTimeoutException` |
| `Future.get(timeout)` hết hạn | Người chờ chưa nhận result đúng hạn | `TimeoutException`; operation có thể còn pending |
| Buffer đích read-only | Invalid read argument | `IllegalArgumentException` |
| Executor/channel group shutdown | Không thể dispatch I/O | `ShutdownChannelGroupException` hoặc lỗi liên quan theo giai đoạn |

**Không dùng một catch `IOException` để nghĩ đã bắt tất cả:** `ReadPendingException`, `NotYetConnectedException`, `AlreadyConnectedException`, `UnresolvedAddressException` là unchecked. Ngược lại, lỗi I/O bất đồng bộ có thể bị bọc trong `ExecutionException` khi dùng Future.

### 13.1. Failure ở lúc initiate so với lúc complete

Ví dụ gọi `channel.read(dst)` khi chưa connected có thể ném `NotYetConnectedException` **ngay tại lời gọi**. Nhưng nếu connect bắt đầu hợp lệ rồi không thể hoàn tất, `Future<Void>.get` có thể ném `ExecutionException` với cause là `IOException`.

Handler có hai nhánh:

```java
new CompletionHandler<Integer, MyState>() {
    @Override
    public void completed(Integer n, MyState state) {
        // Operation đã hoàn tất thành công; vẫn xét n.
    }

    @Override
    public void failed(Throwable error, MyState state) {
        // Operation đã thất bại; không giả lập n=-1.
    }
}
```

Đây là **mảnh minh họa**, `MyState` phải do app định nghĩa và operation được initiate với handler này.

### 13.2. Exception cụ thể có thể phụ thuộc OS

`ConnectionRefusedException` không phải một loại exception Java chuẩn luôn được trả trong mọi trường hợp TCP connect failure. Java thường báo một `IOException` (có thể có message “Connection refused” trên một OS, hoặc lỗi khác ở môi trường khác).

Vì vậy, không so chuỗi của `IOException.getMessage()` để quyết định correctness nghiệp vụ. Dùng exception types, trạng thái operation, policy retry và metrics.

## 14. Một read pending + một write pending được hỗ trợ

`AsynchronousSocketChannel` cho phép **một lượt đọc và một lượt ghi đang chờ cùng lúc** trên cùng socket.

Ví dụ:

```java
Future<Integer> readFuture = socket.read(input);
// Trước khi readFuture hoàn tất, vẫn có thể:
Future<Integer> writeFuture = socket.write(output);
```

Đây là mảnh minh họa. Hai buffers riêng `input`, `output`. Cần quản lý completion của cả hai.

Nhưng nếu gọi:

```java
Future<Integer> first = socket.read(buffer1);
Future<Integer> second = socket.read(buffer2);
```

trong khi `first` chưa hoàn tất, lời gọi read thứ hai sẽ ném `ReadPendingException`.

Tương tự: một write chưa hoàn tất mà khởi tạo write thứ hai sẽ gây `WritePendingException`. Không cố tình kích hoạt `WritePendingException` trong integration test bằng hai writes rất nhỏ: write thứ nhất có thể hoàn tất trước khi lệnh thứ hai chạy, nên test sẽ không ổn định.

### 14.1. Tại sao pending operations cần bộ nhớ riêng?

Ngoài giới hạn một read/one write trên socket, ByteBuffers của operations bất đồng bộ không an toàn khi bị truy cập song song. Không dùng **cùng một** buffer làm input và output của hai operations đồng thời.

Với các requests khác nhau trên cùng connection, phải có **một protocol state machine** điều phối đọc frame, parse, ghi response và lập lịch thông điệp kế tiếp. Thread safety của channel không tự giải quyết ordering của application messages.

## 15. Chương trình D — PendingReadDemo.java

Bắt đầu một read khi chưa gửi dữ liệu, thử read lần hai để nhận `ReadPendingException`; trong lúc lượt đọc còn pending, server vẫn gửi một byte sang client. Sau đó client gửi một byte khiến read đầu hoàn tất.

```java
import java.io.*;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public final class PendingReadDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open();
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            Future<AsynchronousSocketChannel> incoming = listener.accept();
            client.connect((InetSocketAddress) listener.getLocalAddress())
                    .get(5, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel server =
                         incoming.get(5, TimeUnit.SECONDS)) {
                ByteBuffer target = ByteBuffer.allocate(1);
                Future<Integer> first = server.read(target);

                boolean rejected = false;
                try {
                    server.read(ByteBuffer.allocate(1));
                } catch (ReadPendingException expected) {
                    rejected = true;
                }

                int write = server.write(ByteBuffer.wrap(
                    "Q".getBytes(StandardCharsets.US_ASCII)))
                    .get(5, TimeUnit.SECONDS);

                ByteBuffer inbound = ByteBuffer.allocate(1);
                client.read(inbound).get(5, TimeUnit.SECONDS);
                client.write(ByteBuffer.wrap(
                    "R".getBytes(StandardCharsets.US_ASCII)))
                    .get(5, TimeUnit.SECONDS);

                int firstRead = first.get(5, TimeUnit.SECONDS);
                target.flip();

                System.out.println("secondReadRejected=" + rejected);
                System.out.println("writeWhileReadPending=" + (write == 1));
                System.out.println("clientReceived=" +
                        (char) inbound.get(0));
                System.out.println("firstRead=" + firstRead);
                System.out.println("firstByte=" + (char) target.get());
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 PendingReadDemo.java
java PendingReadDemo
```

**Stdout đã kiểm chứng:**

```text
secondReadRejected=true
writeWhileReadPending=true
clientReceived=Q
firstRead=1
firstByte=R
```

### 15.1. Vì sao test đáng tin?

Server read đầu đang chờ một byte và client chưa gửi, nên read thứ hai được gọi khi read đầu còn pending. Sau đó server gửi `Q` sang client **theo chiều khác**, chứng minh read và write có thể cùng outstanding. Client gửi `R` để hoàn tất read đầu.

Trong production, nếu connection bị đóng/timeout ngay khi một read đang pending, operation có thể fail thay vì nhận dữ liệu. Test chỉ cô lập đúng hành vi pending-read trên loopback.

## 16. Kênh chưa connected: lỗi không phải EOF

Một socket mới mở chưa có remote peer. Khi `read`/`write`, exception `NotYetConnectedException` báo **trạng thái vòng đời sai**, không trả `-1`.

### 16.1. Chương trình E — UnconnectedChannelDemo.java

```java
import java.nio.*;
import java.nio.channels.*;

public final class UnconnectedChannelDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {
            boolean read = false, write = false;

            try {
                client.read(ByteBuffer.allocate(1));
            } catch (NotYetConnectedException expected) {
                read = true;
            }

            try {
                client.write(ByteBuffer.wrap(new byte[] {1}));
            } catch (NotYetConnectedException expected) {
                write = true;
            }

            System.out.println("readNotConnected=" + read);
            System.out.println("writeNotConnected=" + write);
            System.out.println("isOpen=" + client.isOpen());
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 UnconnectedChannelDemo.java
java UnconnectedChannelDemo
```

**Stdout đã kiểm chứng:**

```text
readNotConnected=true
writeNotConnected=true
isOpen=true
```

Chương trình cho thấy **open ≠ connected**. Channel vẫn open cho đến cuối try block, nhưng không thể đọc/ghi stream khi chưa connect thành công.

## 17. Khi ByteBuffer rỗng: kết quả 0, không phải EOF

Nếu destination buffer có `remaining()==0`, `read` có thể hoàn tất ngay với `0` mà không có một I/O network operation.

Điểm này quan trọng khi app dùng buffer cố định rồi quên gọi `clear` hoặc đã fill buffer nhưng vẫn tiếp tục `read`:

```java
ByteBuffer b = ByteBuffer.allocate(1);
b.put((byte) 42);
Future<Integer> f = channel.read(b); // remaining()==0.
```

Đây là mảnh minh họa. Kết quả 0 không có nghĩa peer đã gửi EOF. Với frame reader, trước khi gọi `read` cần bảo đảm destination **còn chỗ chứa**, hoặc tiêu thụ/compact dữ liệu phù hợp.

### 17.1. Chương trình F — EmptyBufferDemo.java

```java
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public final class EmptyBufferDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open();
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            Future<AsynchronousSocketChannel> incoming = listener.accept();
            client.connect((InetSocketAddress) listener.getLocalAddress())
                    .get(5, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel server =
                         incoming.get(5, TimeUnit.SECONDS)) {
                int emptyRead = server.read(ByteBuffer.allocate(0))
                        .get(5, TimeUnit.SECONDS);

                client.write(ByteBuffer.wrap(
                    "Z".getBytes(StandardCharsets.US_ASCII)))
                    .get(5, TimeUnit.SECONDS);

                ByteBuffer target = ByteBuffer.allocate(1);
                int n = server.read(target).get(5, TimeUnit.SECONDS);
                target.flip();

                System.out.println("emptyRead=" + emptyRead);
                System.out.println("realRead=" + n);
                System.out.println("byte=" + (char) target.get());
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 EmptyBufferDemo.java
java EmptyBufferDemo
```

**Stdout đã kiểm chứng:**

```text
emptyRead=0
realRead=1
byte=Z
```

`emptyRead=0` không phải close/error. Sau đó client gửi `Z`, server đọc được một byte bằng buffer có remaining. Dùng `remaining()` để diễn giải `0`.

## 18. Đóng socket khi một read đang pending

`AsynchronousSocketChannel.close()` là thao tác quản lý resource, không phải một ký hiệu EOF application tự động cho mọi tình huống. Nếu socket đang đợi read mà thread khác close, pending read có thể hoàn tất **thất bại** với một exception liên quan channel đóng, thay vì trả `-1`.

### 18.1. Vì sao close khác remote orderly FIN?

- Remote orderly `shutdownOutput`: read có thể nhận bytes còn lại rồi `-1`.
- Local close khi read còn pending: local operation không còn resource để tiếp tục, thường fail.
- Remote reset/đứt bất thường: read/write có thể fail bằng `IOException`, không nhất thiết EOF.

Không nên gom cả ba thành một trạng thái “đã đọc đủ dữ liệu”.

### 18.2. Chương trình G — PendingCloseDemo.java

```java
import java.io.*;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.util.concurrent.*;

public final class PendingCloseDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open();
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            Future<AsynchronousSocketChannel> incoming = listener.accept();
            client.connect((InetSocketAddress) listener.getLocalAddress())
                    .get(5, TimeUnit.SECONDS);

            AsynchronousSocketChannel server =
                    incoming.get(5, TimeUnit.SECONDS);
            try {
                Future<Integer> pending =
                        server.read(ByteBuffer.allocate(2));
                server.close();

                boolean failed = false, io = false;
                try {
                    pending.get(5, TimeUnit.SECONDS);
                } catch (ExecutionException expected) {
                    failed = true;
                    io = expected.getCause() instanceof IOException;
                }

                System.out.println("readFailedAfterClose=" + failed);
                System.out.println("failureIsIOException=" + io);
                System.out.println("serverIsClosed=" +
                        (!server.isOpen()));
            } finally {
                server.close();
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 PendingCloseDemo.java
java PendingCloseDemo
```

**Stdout đã kiểm chứng trên môi trường thử:**

```text
readFailedAfterClose=true
failureIsIOException=true
serverIsClosed=true
```

Trong test, server read đang đợi 2 byte và peer chưa gửi. Server bị đóng, Future hoàn tất thất bại với cause thuộc `IOException`.

**Không hardcode subclass cụ thể trong mọi môi trường** cho mọi cách shutdown/reset network. `AsynchronousCloseException` là một lỗi có thể gặp khi channel bị đóng trong I/O, nhưng yêu cầu nghiệp vụ chỉ nên coi đây là operation failure và xử lý lifecycle cho đúng.

## 19. Timeout: hai ngữ nghĩa phải tách bạch

Có hai kiểu timeout thường bị nhầm:

### 19.1. Timeout của người chờ Future

```java
Future<Integer> pending = channel.read(dst);
int n = pending.get(5, TimeUnit.SECONDS);
```

Đây là mảnh minh họa. Nếu `get` ném `TimeoutException`, **người chờ** chưa nhận kết quả đúng hạn, nhưng **read có thể vẫn pending**. Vì vậy:

- Không khởi tạo read thứ hai vô điều kiện, có thể gặp `ReadPendingException`.
- Không clear/recycle buffer khi read cũ còn dùng nó.
- Không xem TimeoutException là đã nhận EOF.
- Có cancellation/close policy rõ, đặc biệt trước khi retry.

### 19.2. Timeout đặt vào chính asynchronous socket read

```java
channel.read(
        dst,
        500, TimeUnit.MILLISECONDS,
        attachment, completionHandler);
```

Đây là mảnh minh họa. Nếu timeout của operation hết trước khi hoàn tất, handler `failed` nhận `InterruptedByTimeoutException`. Tài liệu Java 17 cảnh báo:

- **Trạng thái `ByteBuffer` sau timeout là không được xác định.**
- Implementation có thể đặt chiều read/write vào trạng thái lỗi nếu không thể bảo đảm thao tác chưa truyền bytes.
- Lần I/O tiếp theo ở chiều đó có thể ném unchecked runtime exception không được chỉ định cụ thể.
- Không “retry như không có gì xảy ra” trên buffer/connection ấy nếu protocol cần correctness.

Một cách recovery an toàn thường là **đóng connection bị timeout, giải phóng buffers theo quy trình và khởi tạo lại request trên connection mới khi nghiệp vụ cho phép**. Retry cần idempotency vì remote có thể đã nhận một phần request trước khi timeout.

### 19.3. Timeout ≤ 0 nghĩa là không đặt giới hạn operation

Theo `AsynchronousSocketChannel` Java 17, overload timeout xử lý các giá trị **≤0** như **không timeout**. Không tự truyền 0 rồi nghĩ sẽ có timeout ngay lập tức.

## 20. Chương trình H — TimedReadDemo.java

Đây là test riêng cho timeout của **socket operation**, không phải `Future.get`. Kết nối loopback được thiết lập nhưng peer không gửi byte; server bắt đầu read với timeout 80ms, handler nhận lỗi rồi chương trình đóng socket.

```java
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.util.concurrent.*;

public final class TimedReadDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open();
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            Future<AsynchronousSocketChannel> incoming = listener.accept();
            client.connect((InetSocketAddress) listener.getLocalAddress())
                    .get(5, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel server =
                         incoming.get(5, TimeUnit.SECONDS)) {
                CompletableFuture<Throwable> result =
                        new CompletableFuture<>();

                server.read(
                    ByteBuffer.allocate(1),
                    80, TimeUnit.MILLISECONDS,
                    null,
                    new CompletionHandler<Integer, Void>() {
                        public void completed(Integer n, Void a) {
                            result.complete(
                                new IllegalStateException(
                                    "Unexpected " + n));
                        }
                        public void failed(Throwable t, Void a) {
                            result.complete(t);
                        }
                    });

                Throwable t = result.get(5, TimeUnit.SECONDS);
                System.out.println("timedOut=" +
                        (t instanceof InterruptedByTimeoutException));
                System.out.println("failureType=" +
                        t.getClass().getSimpleName());
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 TimedReadDemo.java
java TimedReadDemo
```

**Stdout đã quan sát trên JDK/Windows:**

```text
timedOut=true
failureType=InterruptedByTimeoutException
```

Không dùng output này làm benchmark về độ chính xác 80ms của scheduler. Nó chỉ kiểm rằng timeout được báo vào handler và loại exception phù hợp. Sau đó try-with-resources đóng connection; code không đọc buffer đã tham gia operation sau timeout.

## 21. CompletionHandler: tiếp tục partial read/write bằng state

Với `CompletionHandler<Integer,A>`:

- `completed(n, attachment)` nhận tiến độ **một** operation.
- `failed(error, attachment)` nhận failure.
- Nếu cần thêm bytes, handler phải khởi tạo **operation tiếp** sau khi trước đó hoàn tất.
- State/attachment phải giữ `ByteBuffer`, tiến độ, kích thước frame và kết quả workflow.
- Không dùng một static ByteBuffer chung cho mọi connections.
- Có giới hạn số pending operations, memory, thread/queue và timeout.

### 21.1. Handler phải kết thúc workflow bằng success hoặc failure

Một callback chỉ log exception, không hoàn tất một `CompletableFuture`/promise ứng dụng, có thể khiến caller chờ vô hạn. Ngược lại, nếu `completed(n)` nhận n nhỏ hơn expected nhưng vẫn báo success, đó là silent truncation.

### 21.2. Tránh xử lý nghiệp vụ nặng ngay trong callback

Callbacks có thể chạy trên executor của asynchronous channel group. Blocking DB/HTTP/parsing lớn trong handler khiến các I/O completions khác chậm. Nên chuyển tác vụ nặng sang worker queue có giới hạn, đồng thời điều phối thứ tự per-connection.

### 21.3. Hạn chế khi timeout/cancel

Nếu handler chain đang pending và caller hết thời hạn, không tự hủy state/buffer chỉ vì `CompletableFuture.cancel` của tầng application được gọi. Đây là future do app tự tạo, không tự đảm bảo cancel underlying socket I/O. Có ownership/cancellation policy rõ.

## 22. Chương trình I — HandlerEchoDemo.java

Ví dụ server dùng `CompletionHandler` để đọc đủ bốn byte `PING` và ghi lại `PONG`; cả read và write callbacks lặp nếu operation chưa chuyển hết buffer.

```java
import java.io.*;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public final class HandlerEchoDemo {
    static final class State {
        final AsynchronousSocketChannel ch;
        final ByteBuffer inbound = ByteBuffer.allocate(4);
        final CompletableFuture<String> done = new CompletableFuture<>();
        int zeros;

        State(AsynchronousSocketChannel ch) {
            this.ch = ch;
        }

        void start() {
            ch.read(inbound, this, new CompletionHandler<Integer, State>() {
                public void completed(Integer n, State s) {
                    try {
                        if (n == null || n < 0)
                            throw new EOFException("Early EOF");
                        if (n == 0 && ++s.zeros > 16)
                            throw new IOException("Stalled read");
                        if (n > 0) s.zeros = 0;

                        if (s.inbound.hasRemaining()) {
                            s.ch.read(s.inbound, s, this);
                            return;
                        }

                        s.inbound.flip();
                        byte[] a = new byte[s.inbound.remaining()];
                        s.inbound.get(a);
                        String request =
                                new String(a, StandardCharsets.US_ASCII);

                        ByteBuffer out = ByteBuffer.wrap(
                                "PONG".getBytes(StandardCharsets.US_ASCII));

                        s.ch.write(out, s,
                                new CompletionHandler<Integer, State>() {
                            public void completed(Integer w, State state) {
                                try {
                                    if (w == null || w < 0)
                                        throw new IOException("Invalid write");
                                    if (w == 0 && ++state.zeros > 16)
                                        throw new IOException("Stalled write");
                                    if (w > 0) state.zeros = 0;

                                    if (out.hasRemaining()) {
                                        state.ch.write(out, state, this);
                                        return;
                                    }
                                    state.done.complete(request);
                                } catch (Throwable err) {
                                    state.done.completeExceptionally(err);
                                }
                            }

                            public void failed(Throwable err, State state) {
                                state.done.completeExceptionally(err);
                            }
                        });
                    } catch (Throwable err) {
                        s.done.completeExceptionally(err);
                    }
                }

                public void failed(Throwable err, State s) {
                    s.done.completeExceptionally(err);
                }
            });
        }
    }

    static void writeAll(AsynchronousSocketChannel ch, ByteBuffer b)
            throws Exception {
        int zeros = 0;
        while (b.hasRemaining()) {
            int n = ch.write(b).get(5, TimeUnit.SECONDS);
            if (n == 0 && ++zeros > 16)
                throw new IOException("Stalled write");
            if (n < 0)
                throw new IOException("Invalid write");
            if (n > 0) zeros = 0;
        }
    }

    static String readExactly(AsynchronousSocketChannel ch, int len)
            throws Exception {
        ByteBuffer b = ByteBuffer.allocate(len);
        int zeros = 0;
        while (b.hasRemaining()) {
            int n = ch.read(b).get(5, TimeUnit.SECONDS);
            if (n < 0) throw new EOFException("Early EOF");
            if (n == 0 && ++zeros > 16)
                throw new IOException("Stalled read");
            if (n > 0) zeros = 0;
        }
        b.flip();
        byte[] bytes = new byte[b.remaining()];
        b.get(bytes);
        return new String(bytes, StandardCharsets.US_ASCII);
    }

    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open();
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            Future<AsynchronousSocketChannel> incoming = listener.accept();
            client.connect((InetSocketAddress) listener.getLocalAddress())
                    .get(5, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel server =
                         incoming.get(5, TimeUnit.SECONDS)) {
                State state = new State(server);
                state.start();

                writeAll(client, ByteBuffer.wrap(
                        "PING".getBytes(StandardCharsets.US_ASCII)));

                String echo = readExactly(client, 4);
                String seen = state.done.get(5, TimeUnit.SECONDS);

                System.out.println("handlerReceived=" + seen);
                System.out.println("clientResponse=" + echo);
                System.out.println("handlerDone=" +
                        state.done.isDone());
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 HandlerEchoDemo.java
java HandlerEchoDemo
```

**Stdout đã kiểm chứng:**

```text
handlerReceived=PING
clientResponse=PONG
handlerDone=true
```

### 22.1. Vì sao state có ByteBuffer và Future riêng?

Mỗi connection có trạng thái độc lập. Handler read không tạo read thứ hai cho cùng channel **trước completion của lần trước**; handler write cũng không tạo write tiếp cho tới khi lần trước kết thúc.

### 22.2. Một giới hạn của ví dụ

Đây là một frame cố định 4 byte để tập trung vào cách chain partial operations. Production cần parse nhiều frames trên cùng connection, chuyển sang connection shutdown rõ, hỗ trợ backpressure, deadline, validation, lỗi initiate operation, và không xử lý dữ liệu lớn trong callback.

## 23. Accept cũng là thao tác bất đồng bộ một-at-a-time

`AsynchronousServerSocketChannel` chỉ cho phép **một outstanding `accept`** trên cùng listener.

Nếu gọi `accept()` khi một accept khác chưa hoàn tất, Java ném `AcceptPendingException`. Điều này không cấm server quản lý **nhiều client cùng lúc**: sau khi một connection được accept, listener có thể đăng ký accept tiếp, còn accepted sockets được xử lý độc lập.

### 23.1. Chương trình J — AcceptPendingDemo.java

```java
import java.net.*;
import java.nio.channels.*;
import java.util.concurrent.*;

public final class AcceptPendingDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open();
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            Future<AsynchronousSocketChannel> pending =
                    listener.accept();

            boolean duplicate = false;
            try {
                listener.accept();
            } catch (AcceptPendingException expected) {
                duplicate = true;
            }

            client.connect(
                    (InetSocketAddress) listener.getLocalAddress())
                    .get(5, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel peer =
                         pending.get(5, TimeUnit.SECONDS)) {
                System.out.println("acceptPendingRejected=" + duplicate);
                System.out.println("acceptedConnected=" +
                        (peer.getRemoteAddress() != null));
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 AcceptPendingDemo.java
java AcceptPendingDemo
```

**Stdout đã kiểm chứng:**

```text
acceptPendingRejected=true
acceptedConnected=true
```

Bài học: một accept pending không đồng nghĩa server “chỉ hỗ trợ một client cả đời”. Mỗi lần accept hoàn tất, có thể initiate accept mới; nhưng phải có giới hạn số connections, số read/write operations, bộ nhớ và cleanup.

## 24. shutdownInput và shutdownOutput theo Java API

Theo tài liệu Java 17:

- `shutdownInput()`: dừng đọc; **những lần read tiếp theo** sẽ trả `-1`. Tác động lên một read đã pending hoặc bytes đang nằm trong receive buffer là **system-dependent**, nên tránh dùng như một cách “flush” dữ liệu.
- `shutdownOutput()`: dừng ghi; **những lần write tiếp theo** sẽ thất bại với `ClosedChannelException`. Tác động lên write đã pending cũng system-dependent.
- Hai method này **không đóng channel**; `isOpen()` có thể vẫn true, vì nửa còn lại còn hoạt động.
- Gọi `shutdownOutput()` khi vẫn còn bytes của response chưa được application gửi hết có thể gây truncation.

### 24.1. Chương trình K — ShutdownDirectionDemo.java

```java
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.util.concurrent.*;

public final class ShutdownDirectionDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open();
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            Future<AsynchronousSocketChannel> pending =
                    listener.accept();
            client.connect(
                    (InetSocketAddress) listener.getLocalAddress())
                    .get(5, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel server =
                         pending.get(5, TimeUnit.SECONDS)) {
                client.shutdownOutput();

                int serverEof = server.read(ByteBuffer.allocate(1))
                        .get(5, TimeUnit.SECONDS);

                boolean blocked = false;
                try {
                    client.write(ByteBuffer.wrap(new byte[] {1}))
                            .get(5, TimeUnit.SECONDS);
                } catch (ExecutionException e) {
                    blocked = e.getCause()
                            instanceof ClosedChannelException;
                }

                server.shutdownInput();
                int localRead = server.read(ByteBuffer.allocate(1))
                        .get(5, TimeUnit.SECONDS);

                System.out.println("peerSawEof=" +
                        (serverEof == -1));
                System.out.println("writeAfterShutdownRejected=" + blocked);
                System.out.println("readAfterShutdownInputIsEof=" +
                        (localRead == -1));
                System.out.println("channelStillOpen=" +
                        client.isOpen());
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ShutdownDirectionDemo.java
java ShutdownDirectionDemo
```

**Stdout đã kiểm chứng:**

```text
peerSawEof=true
writeAfterShutdownRejected=true
readAfterShutdownInputIsEof=true
channelStillOpen=true
```

Đây là test trên socket không có pending writes trong lúc shutdown, tránh suy đoán những tình huống Java docs gọi system-dependent. Future write sau shutdown output thất bại với `ExecutionException` có cause là `ClosedChannelException` trên runtime thử.

## 25. Kết nối tới địa chỉ chưa resolve

`InetSocketAddress.createUnresolved(host,port)` tạo address object chưa được DNS resolve. Gọi `AsynchronousSocketChannel.connect(unresolvedAddress)` sẽ ném `UnresolvedAddressException` tại thời điểm initiate.

Không nhầm lỗi này với DNS lookup failure nói chung: nếu ứng dụng chủ động tạo unresolved address, API có đủ lý do từ chối trước khi kết nối. Khi dùng tên host thực tế, cần quy định cơ chế resolve, thời hạn, địa chỉ IPv4/IPv6 và retry riêng.

### 25.1. Chương trình L — UnresolvedConnectDemo.java

```java
import java.net.*;
import java.nio.channels.*;

public final class UnresolvedConnectDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {
            boolean rejected = false;
            try {
                client.connect(
                    InetSocketAddress.createUnresolved(
                            "invalid.example", 12345));
            } catch (UnresolvedAddressException expected) {
                rejected = true;
            }
            System.out.println("unresolvedRejected=" + rejected);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 UnresolvedConnectDemo.java
java UnresolvedConnectDemo
```

**Stdout đã kiểm chứng:**

```text
unresolvedRejected=true
```

Chương trình không thực hiện DNS query cho host `invalid.example`; chính `createUnresolved` tạo object chưa resolved để minh họa precondition.

## 26. Connection refused và lỗi connect qua Future

Nếu client cố connect tới một endpoint không có listener hoặc bị network/firewall chặn, `connect` có thể thất bại. Khi dùng:

```java
Future<Void> connecting = client.connect(remote);
try {
    connecting.get(5, TimeUnit.SECONDS);
} catch (ExecutionException e) {
    Throwable cause = e.getCause();
    // IOException, tùy OS/provider/điều kiện network.
}
```

Đây là **mảnh minh họa**. Java docs quy định nếu connect operation thất bại, channel sẽ được **đóng**. Vì vậy, để retry, thường tạo **socket mới** rồi connect lại; không reuse channel đã fail.

### 26.1. Không dựa vào một message lỗi cố định

Cùng một endpoint có thể bị refused, unreachable, reset, timed out hoặc can thiệp bởi firewall. IOException cụ thể, cause và message thay đổi theo OS/network. Không viết logic:

```java
if (error.getMessage().contains("Connection refused")) {
    // Không đủ portable để là cơ sở duy nhất của retry policy.
}
```

Thay vào đó phân loại lỗi I/O, kết quả đã biết của request, idempotency và thời hạn retry.

### 26.2. Chương trình M — ConnectRefusalDemo.java

Chương trình dùng `ServerSocket` ngắn hạn xin một port loopback, đóng ngay rồi thử connect tới port ấy. Trên môi trường thử, khi không còn listener, connect bị từ chối. **Test có race**: tiến trình khác về lý thuyết có thể chiếm port vừa giải phóng. Do đó stdout ghi dưới là kết quả quan sát, không phải assertion bất biến cho mọi môi trường.

```java
import java.net.*;
import java.nio.channels.*;
import java.util.concurrent.*;

public final class ConnectRefusalDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        int port;
        try (ServerSocket reserved = new ServerSocket(0, 1, loopback)) {
            port = reserved.getLocalPort();
        }

        try (AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {
            boolean failed = false;
            String cause = "";
            try {
                client.connect(new InetSocketAddress(loopback, port))
                        .get(3, TimeUnit.SECONDS);
            } catch (ExecutionException e) {
                failed = true;
                cause = e.getCause().getClass().getSimpleName();
            }

            System.out.println("connectionFailed=" + failed);
            System.out.println("failureCause=" + cause);
            System.out.println("closedOnFailure=" +
                    (!client.isOpen()));
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ConnectRefusalDemo.java
java ConnectRefusalDemo
```

**Stdout đã quan sát trên JDK/Windows:**

```text
connectionFailed=true
failureCause=IOException
closedOnFailure=true
```

`failureCause=IOException` là tên class thực tế trong lần thử, **không phải quy tắc Java luôn chọn đúng tên đó** cho mọi lỗi connect. Phần có giá trị học tập là **Future báo failure**, và channel bị đóng sau kết nối không thành công.

## 27. Xử lý zero-progress và backpressure

Một operation read/write có thể nhận `0`. Nếu buffer có remaining nhưng provider liên tục không chuyển byte, vòng lặp:

```java
while (buffer.hasRemaining()) {
    int n = channel.write(buffer).get();
    // Cần xử lý n=0 và hạn thời gian, không busy loop vô hạn.
}
```

là **mảnh minh họa chưa hoàn chỉnh**.

Các hướng xử lý:

- Không initiate read vào buffer đã đầy hoặc write từ buffer đã hết.
- Có deadline tổng cho request, không chỉ timeout mỗi operation.
- Giới hạn zero-progress retries; backoff hoặc schedule theo event nếu phù hợp.
- Giới hạn số outstanding buffers, bytes queued, connections và completed-callback tasks.
- Nếu một connection chậm, không để queue vô hạn làm tràn bộ nhớ.
- Không nuốt `IOException` và tiếp tục gửi trên channel đã hỏng.
- Trả trạng thái lỗi rõ cho caller khi request chưa gửi/đọc đủ.

**Backpressure** là cơ chế điều tiết producer khi consumer/network chậm. `AsynchronousSocketChannel` không tự biến mọi queue ứng dụng thành bounded queue.

### 27.1. Ghi thành công có thể chỉ là local progress

Số byte write trả về là tiến độ ở tầng asynchronous channel, không chứng minh peer đã nhận trọn business message. Nếu application cần đúng-một-lần/đã-commit, phải dùng request ID, response/ACK, persisted state và idempotency. TCP đảm bảo truyền luồng có thứ tự khi connection hoạt động bình thường, nhưng ứng dụng vẫn phải xử lý failure **sau khi gửi mà chưa kịp nhận ACK**.

### 27.2. Một lần close không bảo đảm remote đã đọc hết bytes

Đừng gọi write một lần rồi `close` ngay và giả định phía kia đã xử lý. Nếu cần end-of-message/ACK, phải đợi writeAll, đọc response theo protocol và shutdown có trật tự.

## 28. Recovery và retry sau lỗi kết nối

Để thiết kế reconnect/retry:

1. Phân biệt lỗi **trước connect**, lỗi **khi connect**, lỗi **khi gửi body**, lỗi **khi nhận response**.
2. Nếu connect thất bại, **channel đã đóng**; tạo channel mới nếu retry.
3. Nếu write có thể đã gửi một phần request, không tự retry toàn bộ trên connection mới mà thiếu idempotency strategy.
4. Nếu read gặp EOF trước khi đủ frame, báo truncated response, không trả payload giả.
5. Nếu read gặp `IOException` sau khi nhận một phần response, caller phải biết response chưa hoàn tất.
6. Với timeout của socket operation, buffer có thể undefined; thường phải hủy connection và tái tạo state thay vì reuse không an toàn.
7. Áp dụng bounded exponential backoff/jitter khi thích hợp, không retry vô hạn.
8. Không retry lỗi precondition như `NotYetConnectedException` theo kiểu spin; sửa lifecycle.
9. Log đúng exception category và state (connect/read/write, bytes transferred, request ID) nhưng tránh tiết lộ secrets/payload.
10. Giới hạn số kết nối, pool resources, executor threads và deadlines.

### 28.1. Phân biệt retry an toàn và retry có thể tạo duplicate

- Request idempotent (ví dụ đọc state theo key) có thể dễ retry hơn.
- Request thay đổi trạng thái (ví dụ “trừ tiền”) phải có request ID và deduplication phía server để tránh thực thi hai lần sau lỗi mạng.
- Client nhận EOF khi đang chờ ACK **không chứng minh server chưa thực thi request**.

Đó là vấn đề phân tán ở tầng application, không thể giải quyết bằng việc thay `Future` bằng `CompletionHandler`.

## 29. Scattering/gathering: tối ưu cho nhiều ByteBuffers

`AsynchronousSocketChannel` có overload đọc/ghi nhiều `ByteBuffer` cùng lúc:

```java
channel.read(buffers, offset, length,
        timeout, TimeUnit.MILLISECONDS,
        attachment, handler);

channel.write(buffers, offset, length,
        timeout, TimeUnit.MILLISECONDS,
        attachment, handler);
```

Đây là **mảnh minh họa**, `buffers` là mảng `ByteBuffer[]`, `attachment/handler` phải đúng generic type. Các overload scattering/gathering dùng kết quả **`Long`** trong `CompletionHandler<Long,A>`, không phải Integer như read/write một buffer.

Chúng vẫn tuân theo quy tắc **partial progress**: tổng `remaining` của nhiều buffers là số bytes tối đa, không bảo đảm tất cả được chuyển trong một operation.

Không cần thiết dùng chúng ở ví dụ cơ bản; khi học framing, vẫn phải kiểm được length, xử lý EOF, giới hạn memory và bố trí buffer ownership.

## 30. Các loại lỗi kết nối trong chương trình thực

### 30.1. Không có listener trên địa chỉ đích

Future connect thất bại; caller lấy `ExecutionException.getCause()`. Kênh bị đóng nếu connection không thiết lập được. Kiểm tra endpoint, port, firewall, service discovery và retry policy; không dựa một subclass IOException duy nhất.

### 30.2. Peer đóng chiều ghi nhưng local vẫn muốn đọc thêm body

Read có thể trả `-1`. Nếu framing yêu cầu N bytes mà chỉ nhận được M, báo EOF/truncated. Nếu protocol dùng EOF hợp lệ, coi đó là kết thúc message.

### 30.3. Peer reset kết nối bất thường

Có thể nhận IOException ở read/write hoặc Future completion. Exception loại cụ thể và thời điểm phát hiện phụ thuộc OS. Không biến reset thành một response thành công.

### 30.4. Đóng channel khi còn pending operations

Có thể làm pending operations thất bại. Khi đã close channel, không dùng ByteBuffer đang pending theo logic “chắc chắn bytes chưa đi”; cần quản lý completion/lifecycle theo contract.

### 30.5. Một read hoặc write trùng trên cùng socket

`ReadPendingException` và `WritePendingException` là dấu hiệu state machine không điều phối đúng. Không tiếp tục submit operations cùng chiều cho tới khi operation hiện tại hoàn tất.

### 30.6. Timeout của operation

`InterruptedByTimeoutException` khác `TimeoutException` của Future waiter. Timeout operation có thể làm buffer/channels direction unusable; thường cần close/reconnect.

### 30.7. Race giữa read, shutdown và close

Tác động của shutdown lên **outstanding I/O** có phần system-dependent. Đừng thiết kế sao cho một socket đang có pending write đột nhiên bị shutdown từ thread khác mà vẫn hứa đủ bytes. Dùng sequencing rõ giữa writeAll completion, shutdownOutput và response read.

## 31. Security và production readiness

### 31.1. Không tin length-prefix từ peer

Kiểm độ dài trước khi allocate, giới hạn frame size, tổng bytes, số concurrent requests, tốc độ tối thiểu/timeout và connection quota. Một header có length rất lớn có thể gây resource exhaustion.

### 31.2. Input chưa tin cậy cần decode/parse an toàn

UTF-8 có thể malformed; `CharsetDecoder` cho phép chính sách `CodingErrorAction.REPORT` nếu cần. Không giả định mọi bytes trong frame là một String hợp lệ hoặc deserialize đối tượng Java từ mạng mà thiếu validation/schema.

### 31.3. AsynchronousSocketChannel không tự cung cấp TLS

API là socket TCP theo stream; nó **không tự mã hóa hoặc xác thực peer bằng TLS**. Nếu cần truyền bí mật qua mạng không tin cậy, dùng TLS implementation/wrapper phù hợp như `SSLEngine` với state machine được thiết kế cẩn thận, hoặc thư viện networking/TLS được bảo trì. Đừng coi việc dùng NIO.2 đồng nghĩa an toàn truyền thông.

### 31.4. Bảo vệ ứng dụng khỏi slow clients

Nếu mỗi client giữ một buffer lớn, nhiều connections có thể tạo áp lực memory ngay cả khi không có thread block. Giới hạn số connections, số bytes pending, frame size, deadlines, retries, executors, queue và logging.

### 31.5. Connection lifecycle nên có owner rõ

Một accepted channel phải được đóng đúng một lần theo policy khi request hoàn tất hoặc bị hủy. Listener có lifecycle khác accepted sockets. Nếu dùng `AsynchronousChannelGroup` tự quản lý, phải shutdown group có kiểm soát, tránh hủy tasks còn đang xử lý.

### 31.6. Không dùng môi trường loopback để suy performance Internet

Loopback có độ trễ thấp, không đại diện Internet. Kiểm thử mạng thật cần packet loss/reordering ở tầng TCP/IP (TCP vẫn trình bày stream có thứ tự), connection resets, latency, firewall, TLS, backpressure, DNS và server load. Tính đúng thuật toán phải không dựa trên số reads được chia theo packet.

## 32. Ma trận kiểm thử

| Test | Điều nên xác minh | Điều không được giả định |
| --- | --- | --- |
| Open client socket | Open=true, chưa connected | Open nghĩa là đã kết nối |
| Bind server | Listener có địa chỉ local | Bind trên mọi sandbox luôn được phép |
| Accept client | Trả socket server riêng | Future accept trả luôn listener |
| Read/write 4 bytes | `PING`/`PONG` đúng | Một read luôn trả4 ngay |
| Length-prefix + UTF-8 | Frame 7 bytes round-trip | Một ký tự nằm trọn trong một chunk |
| Buffer 3 bytes | Body 7 bytes cần ≥3 app chunks | OS phát đúng3 TCP packets |
| Read result zero | Không có bytes tiến triển | Zero=EOF |
| Remote half-close | Read hết bytes rồi EOF | Local channel bị đóng hoàn toàn |
| Local shutdownOutput | Write tiếp bị từ chối | Không thể đọc response |
| Local shutdownInput | Read tiếp -1 | Pending read/dữ liệu cũ có behavior cố định |
| Close pending read | Future thất bại | Luôn trả EOF -1 |
| ReadPending | Read thứ hai bị từ chối | Hai reads cùng chiều tự chạy song song |
| Write while read pending | Có thể hoạt động | Có thể thêm read thứ hai |
| AcceptPending | Accept thứ hai khi first pending bị từ chối | Listener cả đời chỉ accept một client |
| Read/write unconnected | NotYetConnected | Lỗi này là EOF |
| Timed operation | InterruptedByTimeoutException | Buffer giữ nguyên sau timeout |
| Future.get(timeout) | Caller hết thời gian chờ | Operation đã bị hủy |
| Unresolved remote address | UnresolvedAddressException | API tự DNS resolve một address bị đánh dấu unresolved |
| Connect to freed local port | Có thể bị refused | Luôn đúng IOException subclass/message |
| Connect failure | Channel bị đóng | Có thể retry trên cùng channel |
| Server EOF trước đủ frame | Báo truncated | Tự pad bytes còn thiếu |
| Partial write | Loop đến drained | Một write tự gửi hết |
| Multiple outstanding buffers | Mỗi op có buffer riêng | Buffer thread-safe vì channel thread-safe |
| Security | Bounded frame, validation, TLS khi cần | TCP NIO.2 mặc định đã mã hóa |

### 32.1. Unit test cho partial result một cách deterministic

Network loopback thường vận chuyển một payload nhỏ trong một read, khiến khó ép provider trả partial result ngẫu nhiên. Thay vì trông chờ OS ngẫu nhiên chia packet, test logic bằng một adapter/fake completion source giả lập kết quả:

```text
write of 6 bytes:
  callback n=2 → remaining4
  callback n=1 → remaining3
  callback n=3 → remaining0 → success

readExactly 6:
  callback n=2 → remaining4
  callback n=2 → remaining2
  callback n=-1 → truncated frame, not success
```

Đây là kịch bản test logic, không phải stdout từ OS. Kết hợp **unit tests synthetic** với **integration tests loopback/network**. Với mạng thật, không assert số `read`/`write` calls hay packet boundaries.

### 32.2. Kết quả kiểm thử có thể khác giữa OS

Các chương trình demo đã chạy thành công trên JDK24 Windows với `--release 17`. Điều này xác minh cách dùng API và stdout **trong môi trường thử**, không hứa khả năng mở loopback socket trên mọi sandbox; exception cụ thể ở connect refusal và timing của timeout có thể thay đổi.

## 33. Lỗi phổ biến cần tránh

1. **Một `write` là một message hoàn chỉnh.** Sai: kiểm `hasRemaining` và loop.
2. **Một `read` nhận đúng message sender đã write.** Sai: TCP là stream, dùng framing.
3. **Bỏ qua `n`.** Sai: dùng `n` thực tế để xác định bytes đã chuyển.
4. **Gọi `read` vào buffer không còn remaining rồi nghĩ peer đã EOF.** Sai: read có thể trả 0.
5. **Gọi `clear` khi buffer còn bytes chưa gửi.** Sai: làm mất dữ liệu.
6. **Gọi `flip` trên buffer vừa wrap chưa put.** Sai: có thể khiến limit=0.
7. **Coi `n==0` và `n==-1` cùng là EOF.** Sai: EOF là -1.
8. **Coi mọi read -1 là lỗi network.** Sai: orderly half-close có thể đúng protocol.
9. **Coi mọi IOException là EOF hợp lệ.** Sai: reset/close/connect failure cần xử lý riêng.
10. **Không kiểm length-prefix.** Sai: nguy cơ OOM/DoS.
11. **Decode riêng các chunks UTF-8.** Sai: cắt giữa bytes của ký tự đa byte.
12. **Gọi hai reads outstanding trên một socket.** Sai: `ReadPendingException`.
13. **Gọi hai writes outstanding trên một socket.** Sai: `WritePendingException`.
14. **Gọi hai accepts outstanding trên listener.** Sai: `AcceptPendingException`.
15. **Gọi read/write trước connect.** Sai: `NotYetConnectedException`.
16. **Thử lại connect trên channel đã fail.** Sai: connect failure đóng channel.
17. **Tưởng `Future.get(timeout)` tự hủy I/O.** Sai: operation có thể pending.
18. **Retry sau timed socket read mà reuse buffer như chưa có gì.** Sai: buffer có thể undefined.
19. **Đóng socket trước khi writeAll hoàn tất.** Sai: có thể truncation/failure.
20. **ShutdownOutput khi còn pending write.** Sai: behavior pending op system-dependent.
21. **Dùng một ByteBuffer cho pending read/write cùng lúc.** Sai: buffer không thread-safe.
22. **Không có response/ACK khi cần xác nhận business success.** Sai: write completion không chứng minh remote commit.
23. **Không đóng accepted sockets.** Sai: leak network resources.
24. **Log full payload có secrets khi exception.** Sai: cần privacy/logging policy.
25. **Cho rằng asynchronous socket mặc định là TLS.** Sai: cần TLS layer riêng.
26. **Dựa vào cause class/message của connection refused.** Sai: OS/provider có thể khác.
27. **Dựa loopback success để kết luận luôn thành công ở production.** Sai: cần test latency, firewall, resets, load.
28. **Retry vô hạn mọi network failure.** Sai: cần bounds, backoff, idempotency và deadline.

## 34. Bài tập thực hành có đáp án gợi ý

**Bài 1.** Client gửi `ABC` và `DEF` trong hai writes. Receiver có được phép đọc `ABCDEF` trong một read? **Có**. TCP không giữ ranh giới các writes.

**Bài 2.** Vì sao `AsynchronousSocketChannel.read` không truyền `long filePosition`? **Vì socket là stream**, không phải file random-access.

**Bài 3.** Source ByteBuffer remaining=10, write trả3. Còn gì? **7 bytes** cần gửi tiếp nếu protocol yêu cầu.

**Bài 4.** Một read với buffer capacity4 trả2. Trước khi parse dữ liệu, gọi method nào? **flip** để limit=2.

**Bài 5.** Bạn muốn đọc đúng8 bytes của frame. Các reads trả3,2,-1. Kết quả? **Truncated frame**, không trả payload 5 byte như success.

**Bài 6.** Read trả0 nhưng buffer.remaining=0. Đó có phải EOF? **Không**.

**Bài 7.** Một socket đã có read pending, thêm read mới: exception nào? **ReadPendingException**.

**Bài 8.** Có thể write trong khi một read đang pending không? **Có**, tối đa một write outstanding khác chiều.

**Bài 9.** Server listener có accept pending, gọi accept nữa? **AcceptPendingException**.

**Bài 10.** Client mở nhưng chưa connect, gọi write? **NotYetConnectedException**.

**Bài 11.** Client shutdownOutput rồi muốn đọc response? **Vẫn có thể đọc** nếu socket còn open và peer gửi response.

**Bài 12.** Client shutdownOutput rồi gọi write tiếp? **ClosedChannelException** theo contract; với Future có thể qua ExecutionException cause.

**Bài 13.** Server đã đọc hết request rồi nhận -1; đó có phải lỗi không? **Tùy protocol**: hợp lệ với EOF-delimited request, lỗi nếu frame còn thiếu.

**Bài 14.** Peer reset đột ngột: có được coi read IOException là -1? **Không**. Xử lý lỗi riêng.

**Bài 15.** Timed `Future.get(1,SECONDS)` timeout thì operation chắc chắn dừng? **Không**.

**Bài 16.** Timeout ngay trong `socket.read(dst,timeout,...)` khiến buffer ở trạng thái nào? **Không được xác định**, có thể phải discard và close.

**Bài 17.** Đọc length prefix=2.000.000.000, bạn có nên allocate ngay? **Không**; validate max frame size và quota.

**Bài 18.** Payload chứa emoji UTF-8 bị chia qua hai chunks. Decode từng chunk rồi nối có an toàn? **Không**; dùng stateful decoder hoặc thu đủ bytes frame trước.

**Bài 19.** Connect thất bại, reuse channel gọi connect tiếp được không? **Không**, thất bại sẽ đóng channel; tạo channel mới.

**Bài 20.** Tại sao response ACK lại quan trọng hơn write completion cho giao dịch? **ACK có thể xác nhận server xử lý** theo contract; write chỉ báo local operation progress.

**Bài 21.** Test này hardcode số lần read=3 có portable không? **Không**. Test final payload/bytes và logic partial với fake adapter.

**Bài 22.** Một service có 100.000 clients, mỗi client giữ buffer64KB, bài toán nào cần giải? **Memory quota/backpressure, connection caps, deadlines và resource ownership**.

**Bài 23.** TCP asynchronous socket tự TLS không? **Không**, phải có TLS layer.

**Bài 24.** Đề xuất loop server đọc frame và trả response: **một accept pending, accepted socket riêng, read header đủ, validate length, read body đủ, writeAll response, deadline, cleanup**.

**Bài 25.** Tại sao dữ liệu gửi qua socket có thể bị xử lý hai lần sau retry? **Client có thể không nhận ACK dù server đã xử lý**; cần request ID và idempotency.

**Bài 26.** Phân biệt `AsynchronousCloseException`, `InterruptedByTimeoutException` và EOF. **Close pending I/O = failure**, timed operation = failure có buffer unsafe, EOF = stream kết thúc thông thường khi đúng protocol.

**Bài 27.** Khi server nhận read -1 nhưng chưa đọc hết body của một frame length-prefix, nên làm gì? **Báo truncated**, ghi logs state, không parse partial thành thông điệp hoàn chỉnh.

**Bài 28.** Read buffer bị fill một phần, muốn chờ thêm bytes của frame, có cần clear buffer không? **Không**, giữ phần đã nhận rồi read tiếp để lấp đủ.

**Bài 29.** Mỗi request cần một connection mới hay có thể tái sử dụng? **Tùy framing và lifecycle**. EOF-delimited request qua shutdownOutput không gửi requests tiếp theo theo chiều đó.

**Bài 30.** Lỗi connect refused có luôn là class `ConnectException` trên mọi OS không? **Không**. Dùng IOException/cause theo kết quả đã nhận và policy phù hợp.

## 35. Checklist trước khi đưa vào sản phẩm

- [ ] Hiểu TCP là byte stream không có ranh giới messages.
- [ ] Dùng protocol framing có độ dài/giới hạn rõ.
- [ ] Listener bind trước accept; client connect trước read/write.
- [ ] Mỗi listener tối đa một accept outstanding.
- [ ] Mỗi socket tối đa một read và một write outstanding.
- [ ] Mỗi operation dùng buffer riêng; không mutate khi pending.
- [ ] Kiểm tra `n>0`, `n==0`, `n==-1` của read.
- [ ] Lặp write đến `!hasRemaining`.
- [ ] Lặp read đến khi đủ frame hoặc EOF; báo truncated đúng lúc.
- [ ] Không gộp IOException, timeout và EOF thành một trạng thái.
- [ ] Phân biệt half-close với close toàn bộ.
- [ ] Không shutdownOutput trước khi các bytes cần gửi đã hoàn tất theo protocol.
- [ ] Xử lý `NotYetConnectedException`/`AlreadyConnectedException`.
- [ ] Xử lý `ReadPendingException`/`WritePendingException`/`AcceptPendingException`.
- [ ] Xử lý kết nối không thành công và không reuse failed channel.
- [ ] Timeout của socket operation có thể khiến ByteBuffer undefined.
- [ ] Timeout của Future.get không mặc định hủy operation.
- [ ] Bắt lỗi ở lúc initiate và ở callback `failed`/Future cause.
- [ ] Giới hạn frame length, memory, queue, connections và CPU.
- [ ] Có deadline tổng, backoff và bounded retries.
- [ ] Có idempotency khi retry request thay đổi trạng thái.
- [ ] Không coi write completion là remote business ACK.
- [ ] Decode UTF-8 qua boundaries đúng cách.
- [ ] Không hardcode packet boundaries hoặc số reads trên mọi OS.
- [ ] Dùng try-with-resources/ownership rõ cho accepted sockets và listener.
- [ ] Không xử lý blocking nghiệp vụ nặng trong completion callback.
- [ ] Dùng TLS khi cần, vì TCP socket NIO.2 không tự mã hóa.
- [ ] Test với loopback, fake partial events và môi trường mạng thực.
- [ ] Chỉ dùng kiến thức hiện hành Java 17+ và ghi rõ tính platform-dependent.

## 36. Tài liệu chính thức đang được sử dụng

- [Java SE 17 — `AsynchronousSocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): lifecycle, connect, one read/one write pending, shutdownInput/output, read/write timeout và buffer state.
- [Java SE 17 — `AsynchronousServerSocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): listener bind/accept, NotYetBound và AcceptPending.
- [Java SE 17 — `AsynchronousByteChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousByteChannel.html): partial read/write, `0` với empty buffer, `-1` EOF và buffer ownership.
- [Java SE 17 — `CompletionHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): callbacks `completed` và `failed`.
- [Java SE 17 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): buffer positions, limits, read/write data, UTF-8.
- [Java SE 17 — `Buffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html): flip, clear, compact, remaining.
- [Java SE 17 — `Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, `get(timeout)`, cancellation.
- [Java SE 17 — `InterruptedByTimeoutException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/InterruptedByTimeoutException.html): timeout trong asynchronous socket operation.
- [Java SE 17 — `ReadPendingException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ReadPendingException.html) và [`WritePendingException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/WritePendingException.html): giới hạn outstanding operations.
- [Java SE 17 — `AsynchronousCloseException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousCloseException.html): close khi có operation đang chờ.
- [Java SE 17 — `AsynchronousChannelGroup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html): nhóm channels và executor resources.

**Kết luận:** `AsynchronousSocketChannel` vận chuyển **dòng byte TCP**, không tự biết mỗi message dài bao nhiêu. Hãy **lặp write cho tới khi hết buffer, lặp read cho tới khi đủ frame hoặc EOF**, hiểu chính xác kết quả `0`/`-1`, và sử dụng `ByteBuffer` đúng trạng thái. `shutdownOutput` tạo kết thúc chiều gửi trong khi có thể vẫn nhận phản hồi; `close` hoặc lỗi mạng là tình huống khác và cần được báo đúng. Khi thao tác bất đồng bộ timeout hoặc bị đóng, không giả định buffer và connection vẫn an toàn để reuse. Phân loại connect/pending/timeout/close errors, đóng resources, áp dụng bounded backpressure và idempotency giúp mã bất đồng bộ đúng dữ liệu trên Java hiện đại.