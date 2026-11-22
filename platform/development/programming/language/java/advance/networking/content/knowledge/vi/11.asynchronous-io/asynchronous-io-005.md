# Java NIO.2: nối tiếp accept, read, xử lý và write mà không mất trạng thái

## 1. Bài toán: I/O bất đồng bộ không đồng nghĩa “quên” công việc đang làm

Một máy chủ TCP cần **chấp nhận kết nối**, **đọc yêu cầu**, **xử lý nghiệp vụ** và **ghi phản hồi**. Khi dùng Java NIO.2 (`AsynchronousServerSocketChannel`, `AsynchronousSocketChannel`), những thao tác này được **khởi chạy bất đồng bộ**: lệnh gọi gửi yêu cầu I/O cho runtime rồi trả quyền điều khiển, và **kết quả tới sau** qua `CompletionHandler` hoặc `Future`. Vì vậy chương trình không thể giả định rằng những dòng lệnh đứng cạnh nhau sẽ tự thực hiện theo thứ tự hoàn tất I/O.

Luồng xử lý đúng cho một request:

~~~text
server.accept(...)
      |
      | accept completed: có AsynchronousSocketChannel của client
      v
Session mới (state riêng cho connection)
      |
      v
read HEADER [đọc cho đủ 4 byte] --partial--> đọc tiếp cùng ByteBuffer
      |
      v
validate length, khởi tạo PAYLOAD buffer
      |
      v
read PAYLOAD [đọc cho đủ length byte] --partial--> đọc tiếp
      |
      v
xử lý message đã hoàn chỉnh
      |
      v
write RESPONSE [ghi cho hết buffer] --partial--> ghi tiếp
      |
      v
cleanup; đóng connection hoặc chuyển trạng thái đọc request mới
~~~

**Ý nghĩa “nối tiếp”:** chỉ bắt đầu bước phụ thuộc khi callback của bước trước xác nhận dữ liệu cần thiết đã đầy đủ. **Ý nghĩa “không làm mất trạng thái”:** giữ nguyên đối tượng phiên, `ByteBuffer.position()`, length, phase, outbound buffer và quyền sở hữu socket qua các callback; không dựng lại dữ liệu mỗi lần callback chạy.

Bài này hướng vào máy chủ TCP với **Java 17+** và NIO.2. Sau bài, bạn sẽ hiểu và viết được pipeline accept → read → process → write, biết cách re-arm accept, xử lý partial transfer, EOF, lỗi, timeout, cleanup và giới hạn tải. Phần mã hoàn chỉnh dùng server bất đồng bộ và client kiểm thử thông thường trên loopback.

## 2. Hai loại “bất đồng bộ” cần phân biệt

### 2.1. NIO non-blocking + Selector

`SocketChannel.configureBlocking(false)` với `Selector` là mô hình **readiness**: bạn được thông báo channel có khả năng thực hiện I/O rồi gọi `read/write`; kết quả có thể là `0` nếu chưa có tiến độ. Ứng dụng trực tiếp quản lý vòng sự kiện và `SelectionKey.OP_READ/OP_WRITE`.

### 2.2. NIO.2 AsynchronousSocketChannel

`AsynchronousSocketChannel` là mô hình **completion**: bạn gọi `channel.read(buffer, attachment, handler)`, sau đó runtime gọi `handler.completed(result, attachment)` khi thao tác hoàn tất, hoặc `handler.failed(error, attachment)` khi thất bại. Ứng dụng viết bước tiếp theo trong callback, không yêu cầu tự gọi `Selector.select()`.

| Tiêu chí | NIO + Selector | NIO.2 Asynchronous channels |
| --- | --- | --- |
| Nhận kết nối | `ServerSocketChannel.accept` sau OP_ACCEPT | `AsynchronousServerSocketChannel.accept` + handler |
| Đọc | `SocketChannel.read` khi OP_READ | `AsynchronousSocketChannel.read` + completion callback |
| Ghi | `SocketChannel.write` khi OP_WRITE | `AsynchronousSocketChannel.write` + completion callback |
| Kết quả | Trả về tại thời điểm gọi | Được trả về sau qua callback hoặc `Future` |
| Phần công việc dở | Buffer, parser state, outbound queue | Buffer, parser state, trạng thái phiên gắn với callback |
| Thread của handler | Do ứng dụng tổ chức event loop | Do nhóm luồng I/O của asynchronous channel provider tổ chức |
| Có thể có partial I/O? | Có | Có |
| Cần deadline/giới hạn tải? | Có | Có |

**Không trộn API** theo cảm tính: `AsynchronousSocketChannel` không có `register(selector, ...)` để dùng như `SocketChannel`; ngược lại, gọi `SocketChannel.read` không có nghĩa callback completion sẽ được phát tự động.

## 3. Các API tạo chuỗi accept → read → write

### 3.1. Accept bất đồng bộ

~~~java
AsynchronousServerSocketChannel server =
        AsynchronousServerSocketChannel.open()
                .bind(new InetSocketAddress("127.0.0.1", 0));

server.accept(state, new CompletionHandler<
        AsynchronousSocketChannel, ServerState>() {
    @Override
    public void completed(AsynchronousSocketChannel peer,
                          ServerState attachment) {
        // peer là socket được accept thành công.
        // Giao nó cho một Session và bắt đầu đọc.
    }

    @Override
    public void failed(Throwable error, ServerState attachment) {
        // Lỗi accept hoặc shutdown; xử lý thích hợp.
    }
});
~~~

Đây là **đoạn minh họa**: `ServerState` là class ứng dụng tự định nghĩa, chưa khai báo trong đoạn trên. Một `accept` không hoàn tất thì **không** có socket client sẵn sàng để đọc. `accept(...)` ở dạng callback trả về ngay, không trả `AsynchronousSocketChannel` trực tiếp. Kết quả đó xuất hiện trong `completed`.

Một listening channel chỉ có thể có **một accept đang pending** tại một thời điểm; gọi thêm `accept` khi một accept chưa hoàn tất có thể gây `AcceptPendingException`. Để tiếp tục nhận các kết nối khác sau khi một lần accept thành công, **đăng ký lần accept mới** trong callback hoàn tất, với điều kiện server vẫn đang chạy.

### 3.2. Read bất đồng bộ

~~~java
// peer là AsynchronousSocketChannel được accept.
// header là ByteBuffer đã cấp đủ 4 byte.
// attachment có thể là đối tượng Session.
peer.read(header, attachment, new CompletionHandler<Integer, Session>() {
    @Override
    public void completed(Integer n, Session session) {
        // n: số byte đã đọc, hoặc -1 nếu EOF.
        // Nếu header còn remaining thì đọc tiếp; chưa decode vội.
    }

    @Override
    public void failed(Throwable error, Session session) {
        // Cleanup session, log, thông báo lỗi.
    }
});
~~~

Đây cũng là **mã minh họa**. `AsynchronousSocketChannel.read` callback overload trả `void`; `Integer n` trong `completed` là kết quả của **một hoạt động đọc**, chưa chắc đã đủ dữ liệu cho một trường 4 byte. Nếu stream kết thúc, `n == -1`; nếu buffer đích không còn chỗ hoặc một hoạt động hoàn tất mà chưa chuyển byte, `n == 0` không phải EOF. Luôn kiểm tra `buffer.hasRemaining()` và trạng thái protocol.

Khi một lần `read` còn pending, **không khởi chạy read thứ hai trên cùng channel**: có thể gặp `ReadPendingException`. Trong pipeline đơn giản, chỉ re-arm read **từ callback completed** của lần trước, nhờ vậy luôn có tối đa một hoạt động đọc đang chờ.

### 3.3. Write bất đồng bộ

~~~java
// reply đã ở pha đọc: position chỉ tới byte đầu chưa ghi.
peer.write(reply, attachment, new CompletionHandler<Integer, Session>() {
    @Override
    public void completed(Integer n, Session session) {
        // n là số byte đã ghi trong lần này.
        // Nếu reply.hasRemaining() thì viết tiếp.
    }

    @Override
    public void failed(Throwable error, Session session) {
        // Cleanup session, không retry cả frame một cách mù quáng.
    }
});
~~~

`write` có thể hoàn tất chỉ một phần, và `ByteBuffer.position()` tự tăng theo byte đã được channel nhận để gửi. Không có sentinel `-1` dành cho thao tác ghi như bên đọc. Nếu một write còn pending, write thứ hai có thể ném `WritePendingException`; **không cho nhiều callback cùng ghi trên một socket** mà không tuần tự hóa dữ liệu.

### 3.4. Attachment có tác dụng gì?

Chữ ký điển hình:

~~~java
<A> void read(ByteBuffer dst,
              A attachment,
              CompletionHandler<Integer, ? super A> handler)
~~~

Tham số `attachment` giúp truyền **context của một thao tác/connection** vào cả nhánh thành công và thất bại. Ví dụ một `Session` chứa socket, header, payload, response, request ID và trạng thái hiện hành. Cũng có thể dùng inner class hoặc lambda bắt giữ biến final/effectively-final, nhưng một đối tượng Session tường minh thường dễ mở rộng hơn.

**Lưu ý:** attachment không phải nơi runtime tự lưu ranh giới message. Nó chỉ là đối tượng bạn cung cấp; ứng dụng phải quản lý `position`/`limit`, phase và lifecycle đúng cách.

## 4. Quy tắc quản lý trạng thái theo từng kết nối

Với server nhiều client, tuyệt đối tránh biến toàn cục như `static ByteBuffer requestBuffer` rồi cho mọi client cùng ghi vào đó. Mỗi phiên nên có state riêng:

| Trường | Vai trò |
| --- | --- |
| `AsynchronousSocketChannel peer` | Kết nối đang sở hữu |
| `ByteBuffer header` | 4 byte length chưa/đã nhận |
| `ByteBuffer payload` | Dữ liệu yêu cầu đang nhận |
| `ByteBuffer response` | Dữ liệu phản hồi còn chờ ghi |
| `Phase READ_HEADER / READ_PAYLOAD / WRITING / DONE` | Bước hiện hành |
| `requestId`, principal và deadline | Context ứng dụng nếu cần |
| `closed`, `complete` | Tránh cleanup/reply nhiều lần |

Các nguyên tắc:

1. **Mỗi connection một `Session`.** Callback của client A chỉ cập nhật buffer của client A, không dùng buffer của B.
2. **Chỉ chuyển phase khi đủ byte.** Header cần 4 byte; payload cần chính xác length đã xác thực; phản hồi chỉ hoàn tất khi `!response.hasRemaining()`.
3. **Không reset ByteBuffer giữa các partial completions.** `read`/`write` tự cập nhật position. Gọi `flip()` sau khi nhận đủ hoặc sau khi tạo đầy response, **không flip lại sau mỗi chunk**.
4. **Một read đang pending và một write đang pending là những thao tác có hợp đồng riêng.** Đối với pipeline request-response đơn giản, không cần chạy đồng thời nhiều I/O trên cùng hướng.
5. **Callback không được giả định luôn cùng một thread.** Trạng thái chỉ nên có một chủ sở hữu logic; nếu nhiều threads khác cũng truy cập session, phải có đồng bộ/actor mailbox/event queue.
6. **Đường thành công lẫn đường thất bại đều phải dọn tài nguyên.** Một exception sau khi accept không được làm rò rỉ peer socket hoặc kẹt một session ở phase dang dở.

Không nhầm *asynchronous* với *thread-safe*: API trả về qua callback không tự bảo vệ mọi collection/field mà các client handlers chia sẻ.

## 5. Khi accept xong, phải tiếp tục accept đúng cách

Một server chỉ gọi `accept` một lần sẽ chỉ phục vụ một connection. Sau mỗi accept thành công, nếu còn phục vụ, gọi accept tiếp **trước hoặc độc lập với** việc bắt đầu xử lý peer vừa nhận:

~~~java
// Pseudocode Java, giả định server đang mở và running là true.
void acceptNext() {
    server.accept(null, new CompletionHandler<
            AsynchronousSocketChannel, Void>() {
        @Override
        public void completed(AsynchronousSocketChannel peer,
                              Void unused) {
            if (running) {
                acceptNext();  // Re-arm cho connection kế tiếp.
            }
            new Session(peer).readHeader();
        }

        @Override
        public void failed(Throwable error, Void unused) {
            if (running) {
                // Log và quyết định retry/backoff hoặc ngừng server.
            }
        }
    });
}
~~~

Đây là **pseudocode có biến/lớp tự định nghĩa**, không phải chương trình độc lập. Nó minh họa cách **re-arm** accept khi không còn accept pending. Trong dịch vụ thực tế còn phải:

- Kiểm tra `running` một cách thread-safe và xử lý race giữa shutdown/close với callback accept.
- Xử lý nếu `acceptNext()` hoặc tạo/khởi động Session ném exception (đóng `peer` ngay).
- Không retry tức thì vô hạn với lỗi lặp lại của listener; cần backoff hoặc dừng.
- Giới hạn tổng số kết nối bằng connection cap/semaphore, tránh tạo vô hạn Session khi client đến dồn dập.
- Nếu server bị shutdown, socket được accept sát thời điểm shutdown vẫn phải được bàn giao đúng hoặc đóng ngay; không bỏ mặc.

Không bắt đầu một accept **thứ hai** khi accept thứ nhất vẫn pending. Chỗ đúng để gọi lại là callback `completed` của lần accept đã xong, hoặc theo cơ chế điều phối đảm bảo chỉ có một accept in-flight.

## 6. Từ callback sang “state machine” có thể chứng minh đúng

Một kết nối cần nhận frame `4-byte length big-endian + N byte payload`, xử lý text và gửi frame response tương tự. State machine:

~~~text
ACCEPTED
    |
    v
READ_HEADER [header.position < 4]
    | read n > 0, còn thiếu ----> READ_HEADER (cùng buffer)
    | read -1 ------------------> FAIL: EOF trong header
    | đủ 4
    v
VALIDATE_LENGTH [0 <= N <= MAX_FRAME]
    | sai ----------------------> FAIL: malformed frame
    | đúng
    v
READ_PAYLOAD [payload.position < N]
    | read n > 0, còn thiếu ----> READ_PAYLOAD (cùng buffer)
    | read -1 ------------------> FAIL: truncated payload
    | đủ N
    v
PROCESS
    | tạo response ONCE
    v
WRITE_RESPONSE [response.hasRemaining()]
    | write được một phần ------> WRITE_RESPONSE (cùng buffer)
    | write thất bại -----------> FAIL
    | hết remaining
    v
DONE: đóng socket hoặc quay về READ_HEADER cho request kế
~~~

Đây là **thứ tự logic**; callbacks có thể chạy ở những worker threads khác nhau. Điều quan trọng là **hàm read lại sử dụng đúng buffer field đã có**, không cấp buffer header mới khi header chỉ nhận được 1–3 byte.

### 6.1. Header và payload không có ranh giới ở TCP

Giả sử request là:

~~~text
00 00 00 05 | 68 65 6C 6C 6F
length = 5 | UTF-8/ASCII "hello"
~~~

Kết quả một lần `read(header)` có thể chỉ là 1, 2, 3 hoặc 4 byte. Sau khi đủ 4 byte, `header.flip()` và `header.getInt()` mới đọc được length=5. Payload cũng có thể được nhận 2+3 hoặc 1+1+3 byte. `AsynchronousSocketChannel` không đảm bảo mọi lần read đủ toàn bộ `ByteBuffer`.

### 6.2. Buffer position chính là tiến độ

Ví dụ header 4 byte, callback đầu đọc 2 byte:

~~~text
Trước read:
header.position=0; limit=4; remaining=4

completed(n=2):
header.position=2; limit=4; remaining=2
=> gọi peer.read(header, ...) lần kế, KHÔNG flip, KHÔNG clear.

completed(n=2) lần kế:
header.position=4; limit=4; remaining=0
=> header.flip(); getInt() => length đã đầy đủ.
~~~

Với phản hồi, `write` cũng tăng position theo số byte đã ghi:

~~~text
Response 9 byte: [header 4 byte][payload 5 byte]
write completed(n=3) -> position=3, remaining=6
write completed(n=6) -> position=9, remaining=0
=> đã gửi hết vào channel; bây giờ mới đóng/đợi request kế.
~~~

**Không gọi `response.flip()` lại sau partial write.** Làm vậy có thể gửi lặp phần đầu. **Không khởi chạy nhiều write cùng một lúc** trên cùng session để “tăng tốc”: còn có `WritePendingException` và nguy cơ xen kẽ các frame từ các producer.

## 7. Ví dụ Java 17+ hoàn chỉnh: nối accept → read header → read payload → xử lý → write

Đây là một demo **tự chạy trên loopback**, không cần server bên ngoài. Server dùng `AsynchronousServerSocketChannel` và `AsynchronousSocketChannel` với `CompletionHandler`. Hai client test dùng `java.net.Socket` blocking để giữ phần kiểm thử dễ hiểu, không làm thay đổi tính chất **bất đồng bộ của server**.

Protocol demo:

- **Request:** 4 byte `int` big-endian ghi độ dài N (1..1.024), theo sau bởi N byte ASCII.
- **Xử lý:** chuyển ASCII request sang chữ hoa bằng `Locale.ROOT`.
- **Response:** 4 byte big-endian length, theo sau là response ASCII.
- **Vòng đời:** server accept **2 client**, re-arm accept trước khi xử lý client đầu; mỗi Session có buffer riêng; đọc đủ, ghi đủ, đóng peer, đếm hoàn thành.

Số client cố định giúp bài có điểm kết thúc và stdout xác định; production server sẽ có accept loop tiếp tục đến khi shutdown, bộ giới hạn kết nối và chính sách retry/timeout riêng.

Tạo file **AsyncChainDemo.java** với nội dung:

~~~java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class AsyncChainDemo {
    static final int CLIENTS = 2;
    static final int MAX_BYTES = 1024;

    static void acceptNext(
            AsynchronousServerSocketChannel server,
            AtomicInteger accepted,
            AtomicInteger handled,
            CompletableFuture<Void> all) {

        server.accept(null,
                new CompletionHandler<AsynchronousSocketChannel, Void>() {
            @Override
            public void completed(AsynchronousSocketChannel peer,
                                  Void unused) {
                try {
                    if (accepted.incrementAndGet() < CLIENTS) {
                        // Re-arm accept TRƯỚC khi xử lý peer vừa nhận.
                        acceptNext(server, accepted, handled, all);
                    }
                    new Session(peer, handled, all).readHeader();
                } catch (Throwable error) {
                    try {
                        peer.close();
                    } catch (IOException closeError) {
                        error.addSuppressed(closeError);
                    }
                    all.completeExceptionally(error);
                }
            }

            @Override
            public void failed(Throwable error, Void unused) {
                all.completeExceptionally(error);
            }
        });
    }

    static final class Session {
        final AsynchronousSocketChannel peer;
        final AtomicInteger handled;
        final CompletableFuture<Void> all;

        // Không tạo lại các buffer sau một partial completion.
        final ByteBuffer header = ByteBuffer.allocate(4);
        ByteBuffer payload;
        ByteBuffer response;

        Session(AsynchronousSocketChannel peer,
                AtomicInteger handled,
                CompletableFuture<Void> all) {
            this.peer = peer;
            this.handled = handled;
            this.all = all;
        }

        void readHeader() {
            peer.read(header, null, new CompletionHandler<Integer, Void>() {
                @Override
                public void completed(Integer n, Void unused) {
                    try {
                        if (n == -1) {
                            fail(new EOFException("EOF in header"));
                            return;
                        }

                        if (header.hasRemaining()) {
                            // Đã đọc 1..3 byte? Đọc tiếp cùng header.
                            readHeader();
                            return;
                        }

                        header.flip();
                        int length = header.getInt();
                        if (length < 1 || length > MAX_BYTES) {
                            fail(new IOException("Invalid length " + length));
                            return;
                        }

                        payload = ByteBuffer.allocate(length);
                        readPayload();
                    } catch (Throwable error) {
                        fail(error);
                    }
                }

                @Override
                public void failed(Throwable error, Void unused) {
                    fail(error);
                }
            });
        }

        void readPayload() {
            peer.read(payload, null, new CompletionHandler<Integer, Void>() {
                @Override
                public void completed(Integer n, Void unused) {
                    try {
                        if (n == -1) {
                            fail(new EOFException("EOF in payload"));
                            return;
                        }

                        if (payload.hasRemaining()) {
                            // Tiếp tục đọc byte còn thiếu, giữ position.
                            readPayload();
                            return;
                        }

                        payload.flip();
                        byte[] data = new byte[payload.remaining()];
                        payload.get(data);

                        byte[] answer = new String(
                                data, StandardCharsets.US_ASCII)
                                .toUpperCase(Locale.ROOT)
                                .getBytes(StandardCharsets.US_ASCII);

                        response = ByteBuffer.allocate(4 + answer.length);
                        response.putInt(answer.length);
                        response.put(answer);
                        response.flip();
                        writeResponse();
                    } catch (Throwable error) {
                        fail(error);
                    }
                }

                @Override
                public void failed(Throwable error, Void unused) {
                    fail(error);
                }
            });
        }

        void writeResponse() {
            peer.write(response, null, new CompletionHandler<Integer, Void>() {
                @Override
                public void completed(Integer n, Void unused) {
                    try {
                        if (response.hasRemaining()) {
                            // Có thể mới ghi một phần; giữ buffer.
                            writeResponse();
                            return;
                        }

                        // Chỉ hoàn tất sau khi tất cả byte được ghi.
                        peer.close();
                        if (handled.incrementAndGet() == CLIENTS) {
                            all.complete(null);
                        }
                    } catch (Throwable error) {
                        fail(error);
                    }
                }

                @Override
                public void failed(Throwable error, Void unused) {
                    fail(error);
                }
            });
        }

        void fail(Throwable error) {
            try {
                peer.close();
            } catch (IOException closeError) {
                error.addSuppressed(closeError);
            }
            all.completeExceptionally(error);
        }
    }

    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open()
                             .bind(new InetSocketAddress(
                                     InetAddress.getLoopbackAddress(), 0))) {

            int port =
                    ((InetSocketAddress) server.getLocalAddress()).getPort();
            AtomicInteger accepted = new AtomicInteger();
            AtomicInteger handled = new AtomicInteger();
            CompletableFuture<Void> all = new CompletableFuture<>();

            acceptNext(server, accepted, handled, all);

            // Client kiểm thử blocking, server vẫn dùng NIO.2 async.
            for (String request : List.of("hello", "nio2")) {
                try (Socket client = new Socket()) {
                    client.connect(new InetSocketAddress(
                            InetAddress.getLoopbackAddress(), port), 2_000);
                    client.setSoTimeout(3_000);

                    DataOutputStream out =
                            new DataOutputStream(client.getOutputStream());
                    DataInputStream in =
                            new DataInputStream(client.getInputStream());

                    byte[] data =
                            request.getBytes(StandardCharsets.US_ASCII);
                    out.writeInt(data.length);
                    out.write(data);
                    out.flush();

                    int replyLength = in.readInt();
                    if (replyLength < 1 || replyLength > MAX_BYTES) {
                        throw new IOException("Invalid reply length");
                    }
                    byte[] reply = in.readNBytes(replyLength);
                    if (reply.length != replyLength) {
                        throw new EOFException("Short reply");
                    }

                    System.out.println("reply: " + new String(
                            reply, StandardCharsets.US_ASCII));
                }
            }

            // Chờ TỪ main, không chặn một completion handler.
            all.get(5, TimeUnit.SECONDS);
            System.out.println("handled: " + handled.get());
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac -encoding UTF-8 AsyncChainDemo.java
java AsyncChainDemo
~~~

Stdout khi chạy thành công:

~~~text
reply: HELLO
reply: NIO2
handled: 2
~~~

### 7.1. Giải thích tại sao demo không mất trạng thái

1. `server.accept(...)` đăng ký một accept, callback nhận `peer`. Với connection thứ nhất, callback re-arm accept để tiếp tục nhận connection thứ hai.
2. `new Session(peer, ...)` tạo một **header 4 byte riêng** cho mỗi peer. Không dùng buffer global; Session được callback giữ tham chiếu trong suốt pipeline.
3. `readHeader()` gọi `peer.read(header, null, handler)`. Nếu chỉ đọc được 1–3 byte, callback gọi lại `readHeader()` trên **cùng header**, vị trí không reset. Chỉ khi đủ 4 byte mới `flip`, giải mã length và kiểm tra `1..1024`.
4. `readPayload()` cấp buffer đúng length đã kiểm tra. Nếu mới có một phần payload, callback đọc tiếp vào **cùng payload**. Khi đủ byte, `flip` và chuyển byte sang dữ liệu ứng dụng.
5. `PROCESS` tạo câu trả lời in hoa một lần rồi đóng gói response gồm length prefix và bytes. ByteBuffer response được `flip` **một lần** trước khi gửi.
6. `writeResponse()` ghi những byte còn lại. Nếu write mới hoàn tất một phần, callback ghi tiếp từ `response.position()` hiện có, không đóng peer khi còn `hasRemaining()`.
7. Sau khi toàn bộ response được giao cho channel, Session đóng peer và tăng counter. `CompletableFuture all` được hoàn thành khi hai phiên xong. Thread chính chờ `all.get(...)` để demo dừng xác định.

**Quan trọng:** `CompletableFuture` trong code trên dùng để **điều phối khi nào toàn bộ demo xong**, không thay thế các `CompletionHandler` đọc/ghi. Mã client dùng các stream blocking để kiểm tra, còn luồng xử lý phía server hoàn toàn dùng các asynchronous channel.

### 7.2. Vì sao không dựa vào thứ tự callback/thread?

Hai Session có thể được xử lý trên các worker threads khác nhau và callback có thể thay đổi thread giữa các bước. Trong chương trình, mỗi lần callback **sở hữu tiếp** state của Session và chỉ bắt đầu thao tác phụ thuộc sau khi thao tác trước hoàn tất.

Việc in reply theo thứ tự `HELLO` rồi `NIO2` là do **client test gọi lần lượt hai request**, không phải NIO.2 bảo đảm thứ tự xử lý giữa các connection. Nếu hai client chạy đồng thời, thứ tự callbacks phụ thuộc scheduling, I/O và điều kiện tải; nên dùng request ID/state riêng để ghép phản hồi.

### 7.3. Các giới hạn của demo

- Chỉ nhận đúng **hai kết nối**, mỗi kết nối đúng **một request**, rồi đóng; không phải server chạy lâu.
- Mỗi request phải có length trong `1..1024`; zero-length bị từ chối vì **quy tắc của demo**, không phải giới hạn bắt buộc của NIO.2.
- Dùng ASCII và chuyển chữ hoa bằng `Locale.ROOT`; chưa hỗ trợ Unicode normalization, TLS, xác thực hay business logic nặng.
- Ví dụ chỉ có `CompletableFuture.get(5s)` ở main và timeout blocking ở client; chưa cấu hình read/write timeouts **phía server**. Trong production, cần deadline/idle timeout trên session và đóng khi quá hạn.
- Các callback tạo mới đối tượng handler mỗi lần re-arm. Đây là cách đơn giản để học; với tải lớn, cân nhắc giảm allocation, dùng state machine tối ưu hoặc framework phù hợp.
- Khi lỗi bất thường trong callback, `fail` đóng peer và báo Future lỗi. Production cần quy ước log/metrics chi tiết, chống double-close/double-complete và bảo đảm release permits đúng một lần.

Demo được thiết kế để **kiểm tra đúng thứ tự xử lý**, không phải benchmark throughput hay công thức server production.

## 8. Partial read: tại sao một callback không nhất thiết hoàn tất một frame?

Khi yêu cầu đọc 4 byte header, `AsynchronousSocketChannel.read` chỉ hứa kết quả **của lần đọc**. Nó có thể hoàn tất với 1, 2 hoặc 3 byte; khi đó `header.position` đã được tăng tự động, và bạn tiếp tục đọc trong callback. **Không tạo mới `ByteBuffer.allocate(4)` cho mỗi completion**, vì như vậy bỏ mất byte đã nhận.

~~~text
Buffer header:
[ 00 00 00 05 ]
     ^
     header.position sau 2 byte = 2

Lần read kế dùng CHÍNH buffer đó:
peer.read(header, attachment, handler)

Khi header.remaining()==0:
header.flip(); int length=header.getInt();
~~~

Ở trường hợp EOF, `read` trả `-1`. Trong demo, EOF ở header hoặc payload đang đọc được báo lỗi để đơn giản hóa; với protocol nhiều request có thể chấp nhận EOF đúng **ranh giới trước một request mới** như kết thúc phiên bình thường, nhưng EOF giữa header/payload là **truncated frame**.

**`read()==0` không phải EOF.** Với asynchronous I/O, nó có thể xảy ra do buffer trống chỗ nhận (`remaining()==0`) hoặc hoàn tất mà chưa chuyển byte; trong một pipeline xử lý ByteBuffer có giới hạn chính xác, chỉ gọi read khi buffer còn `hasRemaining()`. Nếu hoàn tất với `0` mà vẫn còn remaining, phải giữ state và áp dụng chính sách retry/deadline; không biến `0` thành một frame rỗng hoặc một EOF.

## 9. Partial write: không đóng socket quá sớm

Một sai lầm thường gặp:

~~~java
// SAI: write asynchronous chỉ mới ĐƯỢC KHỞI CHẠY.
peer.write(response, null, handler);
peer.close(); // Có thể đóng trước khi write hoàn tất.
~~~

Một lỗi khác:

~~~java
// SAI: sau mỗi partial write lại flip buffer,
// có thể ghi lặp prefix hoặc payload đã gửi.
peer.write(response, null, handler);
response.flip();
~~~

Cách đúng:

1. Đặt `response` ở pha đọc **một lần** sau `putInt(length)` và `put(payload)`.
2. Gọi `write(response, attachment, handler)`.
3. Trong `completed(n, attachment)`, kiểm tra `response.hasRemaining()`. Nếu true, re-arm write với **cùng buffer**; nếu false, coi hoạt động gửi frame đã hoàn tất ở cấp channel.
4. Chỉ sau đó mới đóng socket hoặc bắt đầu bước cần đợi response gửi hết, tùy protocol.

Việc `write` hoàn tất **không xác nhận receiver đã xử lý nghiệp vụ**. Nó chỉ xác nhận dữ liệu đã được channel ghi theo hợp đồng API. Muốn biết client nhận/xử lý, giao thức cần ACK hoặc phản hồi ứng dụng.

Nếu nhiều message cùng được tạo trên một connection, cần **outbound queue** hoặc một chuỗi Future/completion duy nhất để không khởi chạy nhiều write đè nhau. `WritePendingException` và hiện tượng trộn byte có thể khiến client không còn giải mã được framing.

## 10. Sử dụng attachment để quản lý Phase, request ID và deadline

Một Session production thường có trạng thái rõ ràng:

~~~java
// Minh họa cấu trúc, không phải chương trình chạy độc lập.
enum Phase {
    READ_HEADER, READ_PAYLOAD, PROCESS, WRITE_RESPONSE, DONE, FAILED
}

final class SessionState {
    final AsynchronousSocketChannel peer;
    final ByteBuffer header = ByteBuffer.allocate(4);
    ByteBuffer payload;
    ByteBuffer response;
    Phase phase = Phase.READ_HEADER;
    long deadlineNanos;
    long requestId;

    SessionState(AsynchronousSocketChannel peer) {
        this.peer = peer;
    }
}
~~~

Đoạn trên cần import `java.nio.ByteBuffer` và `java.nio.channels.AsynchronousSocketChannel`. Nó nhấn mạnh các field tồn tại trong **suốt phiên**, chứ không mất sau khi hàm `accept` trả về.

Có thể dùng `session` làm attachment trực tiếp:

~~~java
// Pseudocode: session/handler đã khai báo ở ứng dụng.
session.peer.read(session.header, session, headerHandler);
~~~

Khi callback được gọi, `attachment` vẫn là tham chiếu tới **cùng Session**. Tại callback, bạn có thể đọc `session.phase` và kiểm tra nếu message đang ở phase không mong đợi; nếu phát hiện sai lệch, báo lỗi/đóng để tránh race.

### 10.1. Callback thread không phải transaction lock

Đừng cho rằng vì các thao tác được “nối tiếp” mà mọi dữ liệu dùng chung tự động an toàn. Nếu một thread quản trị có thể đóng Session, còn callback đang ghi reply, phải có **lifecycle guard**, ví dụ `AtomicBoolean closed` hoặc điều phối thay đổi state qua một executor/actor duy nhất.

Một pattern idempotent cleanup:

~~~java
// Minh họa: đặt trong Session, biến closed khởi tạo một lần.
private final AtomicBoolean closed = new AtomicBoolean();

void closeOnce() {
    if (closed.compareAndSet(false, true)) {
        try {
            peer.close();
        } catch (IOException closeError) {
            // Log hoặc thêm suppressed vào lỗi gốc.
        }
        // Release connection permit đúng một lần.
    }
}
~~~

Đoạn này cần import `java.util.concurrent.atomic.AtomicBoolean` và `java.io.IOException`. Gọi `closeOnce()` trong cả success và failure, không release permit ở cả `closeOnce` và callback khác. Với handler idempotent, tránh double-complete Future hoặc double-reply khi timeout và network failure đua nhau.

### 10.2. Dấu hiệu “mất trạng thái”

- Callback đầu nhận 2 byte header; callback sau lại tạo header mới và bỏ 2 byte trước.
- Đã nhận 50 byte payload, retry read với buffer mới `position=0` mà không giữ offset cũ.
- Ghi được 7/100 byte rồi `clear()` response; lần sau gửi lại byte 0.. thay vì byte 7...
- Callback của client A ghi vào biến static requestBuffer, client B sửa buffer trước khi A xử lý.
- Future/callback phản hồi **đã hoàn thành** ngay sau `write(...)`, dù write vẫn pending.
- Một failure path đóng socket nhưng quên xóa session khỏi map hoặc trả semaphore permit.
- Thêm request B vào queue khi request A chưa ghi xong nhưng nhiều writer cùng gửi làm hai response xen byte.

Mỗi lỗi trên có thể tránh bằng **per-connection state + một chủ sở hữu thao tác + định nghĩa rõ điểm chuyển phase**.

## 11. Futures, CompletionHandler và CompletableFuture: chọn cơ chế chuỗi

NIO.2 có thể trả `Future` cho thao tác:

~~~java
Future<Integer> future = peer.read(buffer);
// Ở nơi khác: future.get() sẽ chờ I/O hoàn tất.
~~~

Đây là **mã minh họa**. Nếu gọi `future.get()` ngay trong một I/O completion worker, bạn có thể **chặn** worker đang cần phục vụ những completions khác. Chỉ dùng Future blocking khi luồng gọi thực sự được phép chờ (ví dụ thread main của một chương trình demo), hoặc kết hợp continuation ở một executor phù hợp.

Với `CompletionHandler`:

~~~java
peer.read(buffer, attachment, handler);
// Không đợi ở đây; handler.completed sẽ nối tiếp.
~~~

`CompletableFuture`/`CompletionStage` có `thenCompose` và `thenApply` để mô tả phụ thuộc, nhưng cần hiểu rằng **một lần read chưa chắc nhận đủ frame**. Không chỉ wrap một `read` rồi gọi `thenApply(parseFrame)`, vì parser có thể nhận 1/4 header. Phải viết helper asynchronous **readFully/writeFully** để hoàn tất **đủ số byte**, và chỉ sau đó mới compose bước xử lý.

Khi dùng `thenApply`, business logic chạy trên thread hoàn thành stage theo semantics của CompletionStage; với xử lý CPU/DB lâu, nên dùng `thenApplyAsync` trên executor được quản lý hoặc cơ chế offload thích hợp. Không thực hiện blocking JDBC hoặc phép tính CPU nặng trong callback đọc nếu nó làm nghẽn nhóm worker phục vụ I/O.

## 12. Xử lý lỗi: accept, read, process, write đều cần nhánh failed

### 12.1. Lỗi ở mỗi pha

| Pha | Lỗi/điều kiện | Cách xử lý |
| --- | --- | --- |
| Accept | Listener đóng/shutdown, OS báo lỗi, không còn capacity | Không để client socket rò rỉ; dừng/retry theo chính sách |
| Read header | EOF giữa 4 byte, I/O exception, quá hạn | Báo truncated header; đóng session |
| Validate | Length âm/quá giới hạn, message type/version sai | Từ chối trước cấp phát; đóng hoặc gửi lỗi theo protocol |
| Read payload | EOF giữa N byte, reset, timeout | Không coi payload chưa đủ là frame hợp lệ |
| Process | Parser/logic ném exception, dữ liệu độc hại | Ghi lỗi có ngữ cảnh, không làm chết listener |
| Write | Partial write, write timeout, remote reset | Giữ phần chưa gửi hoặc kết thúc phiên theo chính sách |
| Cleanup | Close/release permit lỗi | Bảo toàn nguyên nhân, cleanup idempotent |

Trong Java, callback `failed(Throwable error, A attachment)` báo lỗi **của I/O operation**. Nhưng logic do bạn viết trong `completed` cũng có thể ném lỗi, và runtime không tự “chuyển” mọi lỗi lập trình đó thành `failed`. Demo đặt `try/catch` trong `completed` rồi gọi `fail` để không bỏ sót cleanup.

Một `SocketTimeoutException` của blocking `Socket` truyền thống không phải luôn là cách NIO.2 báo timeout. Trong asynchronous read/write có timeout, lỗi có thể là `InterruptedByTimeoutException`. Không dùng exception class sai để suy luận về phase.

### 12.2. Timeout và trạng thái I/O không xác định

`AsynchronousSocketChannel` có các overload read/write với tham số thời gian:

~~~java
// Java NIO.2, đoạn minh họa có session và handler tương thích.
peer.read(buffer, 3, TimeUnit.SECONDS, session, readHandler);
peer.write(reply, 3, TimeUnit.SECONDS, session, writeHandler);
~~~

Trong callback `failed`, xử lý timeout cùng với các lỗi I/O. Khi một asynchronous operation bị timeout, **không giả định có thể reuse cùng ByteBuffer và socket một cách an toàn**: một thao tác có thể đã chuyển một phần byte hoặc trạng thái không còn thuận tiện để khôi phục. Với giao thức cần tính đúng đắn chặt, thường nên **đóng phiên** và tái kết nối theo chính sách ứng dụng.

Timeout của một lần read/write không tự là deadline tổng cho **toàn bộ request**. Một peer có thể gửi vài byte trước mỗi timeout và kéo dài vô hạn. Hãy lưu `deadlineNanos` bằng `System.nanoTime()` và kiểm tra thời gian còn lại giữa các pha; dùng scheduled timeout để đóng connection nếu quá ngân sách.

### 12.3. Chỉ hoàn tất promise một lần

Nếu caller chờ một `CompletableFuture<Response>`, nên có một nơi quyết định trạng thái DONE/FAILED. Đóng session, ghi log/metrics và complete/completeExceptionally phải có quy tắc chống đua nhau; hai callbacks hoặc deadline timer có thể cùng cố kết thúc.

`CompletableFuture.complete(...)` trả `false` nếu nó đã hoàn tất trước đó; có thể dùng để quan sát hành vi, nhưng việc release socket/permit vẫn nên ở một guard `closeOnce()`. Không dựa vào `complete` để tự động đóng network resources.

## 13. Khi chạy nhiều client: concurrency và giới hạn tài nguyên

Asynchronous channels không đồng nghĩa “không cần thread”. JDK xử lý I/O completions thông qua provider và nhóm luồng (`AsynchronousChannelGroup`), có thể do bạn chỉ định hoặc để mặc định. Mô hình này giúp code không cần giữ một platform thread bị block trên mỗi client trong cùng cách như blocking thread-per-connection, **nhưng vẫn tốn**:

- File descriptors/sockets và kernel buffers.
- Heap cho `Session`, header/payload/response buffers.
- Workers thực thi callbacks, CPU để parse/serialize và xử lý nghiệp vụ.
- Kết nối tới database/downstream services.
- Hàng đợi application tasks và các yêu cầu chưa được xử lý.

### 13.1. Admission control trước khi bắt đầu Session

Ví dụ đặt giới hạn 100 kết nối active (chỉ là **giá trị minh họa**):

~~~java
// Minh họa tại accept callback, semaphore thuộc server.
Semaphore permits = new Semaphore(100);

// Sau khi accept peer:
if (!permits.tryAcquire()) {
    peer.close(); // Quá tải: đóng ngay, không khởi tạo session.
} else {
    Session session = new Session(peer);
    // Khi Session kết thúc (thành công/lỗi):
    // closeOnce() phải release permit đúng một lần.
    session.readHeader();
}
~~~

Mã minh họa không độc lập và chưa chứa class `Session` thật. `Semaphore` bảo vệ số phiên đang dùng tài nguyên, không chỉ số callback đang chạy. Không acquire permit ở nhánh này rồi release cả trong `failed` và trong `finally` khác mà không có guard.

### 13.2. Outbound backpressure

Nếu client đọc chậm, write sẽ hoàn tất chậm hoặc chỉ một phần. Nếu application cứ tạo response mới và xếp vào hàng đợi vô hạn, bộ nhớ phình to. Cần một outbound queue giới hạn theo **số byte**, giữ offset của từng `ByteBuffer`, và chỉ cho một write đang pending mỗi hướng. Khi queue quá ngưỡng, giảm tốc đọc request, từ chối request mới hoặc đóng phiên theo policy.

Không cố song song hóa nhiều writes lên cùng connection để “giải phóng queue”: thứ tự wire format phải được bảo toàn; nếu protocol yêu cầu multiplexing, cần một bộ serialize chung và request IDs chứ không để các threads ghi tùy ý.

### 13.3. Callback không được làm việc nặng

Một completion handler nên thực hiện lượng công việc nhỏ: xác nhận kết quả, cập nhật state, schedule I/O kế tiếp. Với request cần tính toán lâu, thao tác DB blocking hoặc gọi remote service, chuyển tới executor riêng rồi nối continuation trở lại Session. Nếu xử lý nặng ngay trên completion thread, các kết nối khác có thể bị chậm dù I/O async.

Nhưng **offload không có nghĩa được đồng thời chỉnh cùng ByteBuffer**. Một executor xử lý nghiệp vụ nên tạo response từ **snapshot dữ liệu request đầy đủ**, và chỉ một continuation được quyền cập nhật response buffer/phase khi xử lý xong.

## 14. Shutdown đúng thứ tự

Máy chủ thật cần một đường dừng:

1. Đánh dấu **không nhận kết nối mới** (cờ lifecycle có tính thread-safe).
2. Đóng `AsynchronousServerSocketChannel` để hủy accept pending; callback `failed` lúc shutdown là điều kiện dự kiến, không tự retry vô hạn.
3. Quyết định drain các Session đang hoạt động trong một deadline hay đóng ngay theo SLA.
4. Đóng peer sockets hết hạn, khiến các I/O pending hoàn tất lỗi hoặc được hủy theo API; cleanup session idempotent.
5. Nếu dùng `AsynchronousChannelGroup` tự quản lý, dừng group theo quy trình `shutdown()`/`awaitTermination(...)` rồi `shutdownNow()` khi cần; không đóng group khi còn công việc quan trọng chưa xử lý.
6. Dọn executor business, counters, logging, pending promises và queue. Nếu ứng dụng xử lý idempotent operations, lưu thông tin phục vụ retry/đối soát.

Đừng để callback `accept.failed` tự gọi `acceptNext` mỗi khi listener đóng; nếu vậy có thể tạo vòng lặp lỗi liên tục. Đừng giả định một lệnh `close()` là đã xử lý thành công mọi response chưa gửi.

## 15. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `read` ngay sau `accept(...)` trên biến chưa có peer | Chưa biết socket nào đã được accept | Bắt đầu read trong `accept.completed(peer, ...)` |
| Chỉ gọi accept một lần | Server ngừng nhận client mới sau connection đầu | Re-arm accept trong completion callback |
| Gọi accept lần hai khi lần trước pending | `AcceptPendingException` | Chỉ một pending accept trên listener |
| Một lần read mới chỉ có 1/4 header mà đã decode | `BufferUnderflowException` hoặc frame sai | Đọc lại trên cùng header tới đủ 4 byte |
| Tạo mới header/payload mỗi callback | Mất byte/offset đã nhận | Dùng Session fields và giữ ByteBuffer.position |
| `flip()` response sau partial write | Gửi lặp prefix hoặc payload | Flip một lần, ghi tiếp từ remaining hiện tại |
| Đóng peer ngay sau khi gọi `write` | Response có thể chưa được gửi xong | Đóng trong write completed khi hết remaining |
| Gọi hai read/write cùng hướng khi một operation còn pending | `ReadPendingException`/`WritePendingException` | Serialize các I/O theo hướng và phase |
| Dùng biến static ByteBuffer cho mọi client | Race và trộn byte giữa các phiên | Một Session per connection |
| Dùng `Future.get()` blocking trên completion thread | Cản worker phục vụ các I/O khác | Dùng callback/continuation, offload công việc phù hợp |
| Quên bắt exception trong `completed` | Cleanup không được thực hiện | try/catch và xử lý fail tập trung |
| EOF giữa payload vẫn gọi process | Xử lý frame thiếu byte | Phân biệt EOF tại frame boundary/truncated frame |
| Không kiểm tra length trước cấp phát | DoS hoặc lỗi bộ nhớ | Max frame length, rate/size limits |
| Timer và callback cùng đóng/release | Double cleanup, mất permit | Atomic closeOnce/lifecycle state |
| Re-arm accept vô hạn trong shutdown | Loop lỗi/thử lại vô hạn | Kiểm tra running, không retry khi listener đóng |
| Asynchronous nghĩa là “không cần giới hạn” | Cạn sockets, heap, DB connections | Admission control, queue/buffer limits |
| Gọi write lần tiếp trong callback nhưng tạo response mới | Đổi nội dung đang gửi | Lưu response buffer một lần, dùng remaining |
| Nhầm completion order giữa client A và B | Ghép nhầm response/request | Session riêng, request ID, không dựa vào thứ tự threads |

## 16. Bài tập tự kiểm tra

### Bài A: Header được đọc 1+2+1

Accept thành công, header buffer 4 byte. Ba callbacks read lần lượt trả 1, 2, 1. Khi nào decode length?

**Đáp án:** sau callback thứ ba, khi `header.hasRemaining()==false`. Trước đó giữ nguyên `header.position` và gọi read tiếp cùng buffer. Chỉ sau khi đủ bốn byte mới `flip()` và `getInt()`.

### Bài B: Response 100 byte được ghi 40+0+60

Write callback lần đầu trả 40; lần sau trả 0; lần cuối trả 60. Có được đóng connection sau lần đầu?

**Đáp án:** không. Sau 40 byte, `response.remaining()==60`, nên chưa xong. `0` không phải đóng hoặc thành công toàn bộ; giữ buffer và retry theo completion/deadline. Chỉ khi `remaining()==0` mới hoàn tất wire response ở cấp channel.

### Bài C: Hai client cùng đến

Client A accept xong nhưng đang chờ payload; client B bắt đầu kết nối. Tại sao server có thể accept B trước khi A xử lý xong?

**Đáp án:** sau khi accept A hoàn tất, server re-arm accept mới rồi mới chạy handler A. Các phiên độc lập: B có Session và buffers riêng. Không cần đợi request A hoàn tất để accept B, miễn admission control còn permit.

### Bài D: Client đóng giữa payload

Length được decode là 200, nhưng receiver mới nhận 50 byte rồi read callback trả -1. Có được process 50 byte?

**Đáp án:** không. Payload 200 byte chưa đủ: đây là truncated frame. Đóng session hoặc báo lỗi giao thức; không tự coi EOF là “kết thúc hợp lệ” nếu length còn thiếu.

### Bài E: Chạy cả việc parse CPU nặng trong completion callback

Server có nhiều khách; handler xử lý một thuật toán tốn CPU 2 giây ngay trong `completed`. Điều gì nguy hiểm?

**Đáp án:** worker phục vụ completions bị chiếm 2 giây, có thể làm trễ các phiên khác. Chuyển tác vụ nặng ra executor giới hạn concurrency, giữ snapshot request, rồi điều phối continuation cập nhật đúng Session.

### Bài F: Timeout và write race

Timer timeout đóng peer ngay lúc callback write vừa hoàn tất. Hai nhánh đều gọi `releasePermit()`. Làm sao tránh release hai lần?

**Đáp án:** dùng lifecycle idempotent `closeOnce()`/`AtomicBoolean.compareAndSet`, gom cleanup một nơi, chỉ callback chủ thắng được phép chuyển phase DONE/FAILED. Đóng socket/hủy I/O phải được xử lý là một phần của state machine, không rải các lệnh cleanup tùy ý.

### Bài G: Một lần accept còn pending

Ứng dụng gọi hai `server.accept(...)` liên tiếp mà không chờ completion. Kết quả?

**Đáp án:** với `AsynchronousServerSocketChannel`, mỗi thời điểm chỉ một accept đang pending; lần thứ hai có thể ném `AcceptPendingException`. Chỉ re-arm từ callback khi accept trước đã hoàn tất.

### Bài H: Future.get trong callback

Lập trình viên gọi `peer.read(buffer).get()` từ một completion handler đang chạy trên nhóm worker nhỏ. Tại sao không nên?

**Đáp án:** `get()` là chờ blocking, có thể giữ worker cần cho completions khác, tăng nguy cơ nghẽn hoặc deadlock theo thiết kế nhóm luồng. Nối tiếp bằng callback hoặc mô hình `CompletionStage` không chặn; chỉ chờ trong thread được phép đợi.

## 17. Checklist thiết kế pipeline bất đồng bộ

- [ ] Server có **đúng một accept pending** và re-arm khi accept hoàn thành?
- [ ] Mỗi accepted connection có **Session state riêng**, không dùng shared ByteBuffer không đồng bộ?
- [ ] State ghi rõ phase đọc header, đọc payload, xử lý, ghi response và cleanup?
- [ ] Partial read giữ nguyên ByteBuffer và `position` cho tới khi đủ byte?
- [ ] Frame length được validate trước khi cấp payload buffer?
- [ ] `read==-1` giữa frame được xử lý là truncated, không coi là message hoàn chỉnh?
- [ ] Partial write giữ response buffer và chỉ đóng/chuyển phase khi hết `hasRemaining()`?
- [ ] Không có hai read hoặc hai write pending cùng hướng trên connection?
- [ ] Completion handlers ngắn, không gọi blocking `Future.get()` hay xử lý CPU/DB nặng ngay trong callback?
- [ ] Các callbacks, timers và threads khác chia sẻ state qua cơ chế đồng bộ thích hợp?
- [ ] Có `failed`/try-catch cho mọi pha và cleanup idempotent khi lỗi?
- [ ] Có deadline/idle timeout và giới hạn connection count, frame size, outbound buffers?
- [ ] Shutdown đóng listener, dừng accept, drain/close sessions và ngừng groups/executors đúng thứ tự?
- [ ] Đã test các tình huống 1+3 header, partial payload, partial write, EOF giữa frame, malformed length, client chậm và close giữa callback?

**Kết luận:** NIO.2 cho phép khởi chạy `accept`, `read` và `write` mà không chặn thread gọi, nhưng **trật tự nghiệp vụ không tự xuất hiện**. Để nối tiếp chính xác, chuyển bước **chỉ tại completion**, giữ một **Session** và các **ByteBuffer** xuyên suốt các callback, đọc/ghi đến khi đủ byte, và đóng session đúng một lần. Khi thêm framing, timeouts, giới hạn tài nguyên, error paths và shutdown có kiểm soát, pipeline asynchronous TCP mới đáng tin cậy khi nhiều client cùng hoạt động.