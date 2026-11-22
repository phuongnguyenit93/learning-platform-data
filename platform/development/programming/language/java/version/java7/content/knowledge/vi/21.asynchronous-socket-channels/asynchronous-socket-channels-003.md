# Hoàn tất `connect`, `read` và `write` với kênh mạng bất đồng bộ trong Java

## 1. Bài toán và bức tranh tổng thể

Một ứng dụng mạng có thể cần kết nối đến máy chủ, gửi yêu cầu, nhận phản hồi rồi đóng kết nối. Nếu thread đang phục vụ công việc khác phải **chờ từng thao tác socket**, khả năng phục vụ nhiều kết nối có thể suy giảm. Java NIO.2 cung cấp `java.nio.channels.AsynchronousSocketChannel` để **khởi tạo các thao tác connect, read, write bất đồng bộ** và nhận kết quả thông qua:

1. Một `Future` biểu diễn kết quả chưa hoàn tất; caller quyết định khi nào đợi hoặc kiểm tra.
2. Một `CompletionHandler` mà API gọi theo nhánh `completed` hoặc `failed` khi thao tác xong.

Máy chủ có thể dùng `AsynchronousServerSocketChannel` để nhận các kết nối đến bằng `accept()`. Bài học này tập trung vào **thời điểm hoàn tất `connect`, `read` và `write`**, phân biệt kết quả thành công/thất bại, byte counts, EOF và trạng thái kết nối.

~~~text
SERVER                                  CLIENT
AsynchronousServerSocketChannel         AsynchronousSocketChannel
    |                                         |
 bind(loopback, port=0)                       | open() -> OPEN, NOT CONNECTED
    |                                         |
 accept() -> Future<SocketChannel>            | connect(address)
    |                                         | -> Future<Void>
    |<========= TCP connection ==============|
    |                                         |
 accept completes                      connect completes
    |                                         |
    |                  write("ping") ->       |
    |<=======================================|
 read() -> count > 0                          |
    |                                         |
 write("pong!") ->                            |
    |=======================================>|
    |                                         | read() -> count > 0
    |                                         |
 shutdownOutput()                      read() -> -1 (EOF)
    |                                         |
close both sides after processing             |
~~~

Đây là **sơ đồ khái niệm**, không phải cam kết một lệnh đọc sẽ luôn trả cả chuỗi `ping` hay một lệnh ghi luôn gửi toàn bộ dữ liệu. Socket TCP cung cấp **byte stream**, không có ranh giới thông điệp tự động.

**Chủ đề:** “Hoàn tất connect, read và write” thuộc nhóm “Kênh mạng bất đồng bộ”.

**Tính hiện hành:** `AsynchronousSocketChannel`, `AsynchronousServerSocketChannel`, `AsynchronousChannelGroup`, `CompletionHandler` và `Future` đều là API Java NIO.2 được giới thiệu trong Java 7 và **vẫn được hỗ trợ trong Java 17/21 và các JDK hiện đại**. `CompletableFuture` được giới thiệu sau và vẫn là cách hiện đại để viết adapter callback khi cần composition. Bài chỉ sử dụng kiến thức đang áp dụng, **không sử dụng API lỗi thời hoặc legacy**.

### Bạn sẽ học được

- Trạng thái channel trước/sau connect và các điểm được phép gọi read/write.
- Chính xác kiểu kết quả: `Future<Void>` cho connect, `Future<Integer>` cho read/write, callbacks tương ứng.
- Khi nào connect/read/write hoàn tất, khi nào lỗi được trả qua `get()` hoặc `failed(...)`.
- `read` trả `-1` khi EOF và vì sao cả read/write đều có thể hoàn tất **một phần**.
- Chỉ một read và một write đang pending trên một `AsynchronousSocketChannel`; chúng có thể diễn ra **cùng lúc khác chiều**, nhưng không khởi tạo hai read cùng chiều.
- Phân biệt thời gian chờ `Future.get(timeout)` và timeout thực của overload `read/write(..., timeout, ...)`.
- Thực hiện một chương trình Java 21 **loopback** hoàn chỉnh, có accept, connect callback, Future read/write, callback read/write, EOF và dọn tài nguyên.
- Cách đóng, hủy, xử lý hàng đợi/buffer, TCP framing, backpressure và những sai lầm thường gặp.

## 2. Đúng channel, đúng vai trò

| Kiểu | Vai trò | Hoạt động |
| --- | --- | --- |
| `AsynchronousServerSocketChannel` | Lắng nghe địa chỉ cục bộ | `open()`, `bind()`, `accept()`, `close()` |
| `AsynchronousSocketChannel` | Một kết nối stream đến peer | `open()`, `connect()`, `read()`, `write()`, `shutdownInput()`, `shutdownOutput()` |
| `AsynchronousChannelGroup` | Nhóm channel và pool phục vụ hoạt động bất đồng bộ | Quản lý tài nguyên theo nhu cầu đặc thù |
| `CompletionHandler<V,A>` | Callback hoàn tất | `completed(V result,A attachment)` và `failed(Throwable error,A attachment)` |
| `Future<V>` | Giá trị đại diện một tác vụ đang chờ | `get()`, `get(timeout,unit)`, `isDone()`, `cancel(...)` |
| `ByteBuffer` | Vùng bytes cho đọc/ghi | `wrap`, `allocate`, `position`, `limit`, `flip` |

**Server khác connected socket:** `AsynchronousServerSocketChannel` chỉ lắng nghe. `accept()` trả một `AsynchronousSocketChannel` **mới, đã kết nối**, để đọc/ghi với client. Bạn không gọi `read/write` trên server listening channel.

**Client mới mở chưa connect:** `AsynchronousSocketChannel.open()` tạo channel mở, **chưa kết nối**. Khi gọi read hoặc write trước khi connect thành công, API ném `NotYetConnectedException`. Hãy đợi kết quả connect thành công trước khi submit I/O của phiên giao tiếp đó.

## 3. Chữ ký API: Future và CompletionHandler

### 3.1. Connect

~~~java
Future<Void> pendingConnect = client.connect(remoteAddress);
~~~

Khi `pendingConnect.get()` hoàn tất thành công, nó **trả `null`**, vì kiểu là `Void`. `null` là kết quả bình thường của connect thành công, **không phải** bằng chứng connect thất bại.

Dạng callback:

~~~java
client.connect(remoteAddress, attachment,
        new CompletionHandler<Void, Request>() {
            @Override
            public void completed(Void ignored, Request request) {
                // Kết nối đã thành công: có thể bắt đầu read/write.
            }
            @Override
            public void failed(Throwable error, Request request) {
                // Kết nối thất bại: báo lỗi và dọn request/channel.
            }
        });
~~~

Hai đoạn trên là **minh họa riêng**. `remoteAddress` là `SocketAddress` hợp lệ; `client` là channel chưa connect; `attachment` có kiểu `Request` do ứng dụng định nghĩa. Callback overload trả **`void`**, không trả `Future<Void>`.

### 3.2. Read

~~~java
Future<Integer> pendingRead = socket.read(destination);
socket.read(destination, attachment, readHandler);
~~~

Đây là **hai lựa chọn độc lập**, không thực hiện đồng thời trên cùng buffer/kết nối như ví dụ. `destination` là `ByteBuffer` có chỗ trống. `Integer` nhận qua `Future.get()` hoặc callback có ý nghĩa:

- `>0`: có số byte vừa được đọc.
- `0`: không có byte nào chuyển trong operation đó; **không phải** EOF.
- `-1`: end-of-stream, phía bên kia đã kết thúc luồng gửi một cách quan sát được.
- **Không bảo đảm** số byte trả về bằng `destination.remaining()` ban đầu.

### 3.3. Write

~~~java
Future<Integer> pendingWrite = socket.write(source);
socket.write(source, attachment, writeHandler);
~~~

Đây cũng là **hai lựa chọn độc lập**. `source` chứa bytes muốn gửi, `Integer` cho biết **số byte đã được operation ghi** vào luồng socket. Nếu số byte nhỏ hơn lượng muốn gửi, còn buffer thì phải tiếp tục ghi sau completion. Việc write hoàn tất **không có nghĩa peer đã xử lý thông điệp** hoặc dữ liệu đã được xác nhận ở tầng ứng dụng.

### 3.4. Accept để có peer đã kết nối

~~~java
Future<AsynchronousSocketChannel> nextPeer = server.accept();
AsynchronousSocketChannel accepted = nextPeer.get();
~~~

`server` là `AsynchronousServerSocketChannel` đã bind. Callback overload cũng có:

~~~java
server.accept(attachment,
        new CompletionHandler<AsynchronousSocketChannel, Context>() {
            @Override
            public void completed(AsynchronousSocketChannel peer,
                                  Context context) {
                // peer là connected channel cho client vừa được accept.
            }
            @Override
            public void failed(Throwable error, Context context) {
                // Lỗi accept, cần chính sách phục hồi/đóng.
            }
        });
~~~

Hai đoạn là **minh họa chữ ký**, `attachment` có kiểu `Context` do ứng dụng định nghĩa. Chỉ được có **một accept đang pending trên cùng server channel**; gọi accept lần nữa khi chưa hoàn tất có thể ném `AcceptPendingException`.

### Bảng kiểu kết quả

| Operation | Future overload | CompletionHandler overload |
| --- | --- | --- |
| `connect(remote)` | `Future<Void>`; thành công `get() == null` | `CompletionHandler<Void,A>` |
| `read(dst)` | `Future<Integer>` | `CompletionHandler<Integer,A>` |
| `write(src)` | `Future<Integer>` | `CompletionHandler<Integer,A>` |
| `server.accept()` | `Future<AsynchronousSocketChannel>` | `CompletionHandler<AsynchronousSocketChannel,A>` |

**Đừng nhầm `Future<Void>` với `Future<Integer>`**: connect không trả byte count, còn read/write thì có.

## 4. Hoàn tất connect: chính xác khi nào đọc/ghi được?

Kênh client có các trạng thái học tập:

~~~text
AsynchronousSocketChannel.open()
            |
            v
      OPEN, UNCONNECTED
            |
      connect(remote) initiated
            |
            v
       CONNECT PENDING
          /       \\
         /         \\
    completed     failed
       |             |
       v             v
   CONNECTED       CLOSED
       |
   read/write allowed
       |
 close()
       v
     CLOSED
~~~

Đây là mô hình khái quát theo contract Javadoc Java 21. Khi connect thất bại trong callback, channel được **đóng**. Với Future, `connect(remote).get()` báo lỗi qua `ExecutionException` nếu operation thất bại.

Các điểm quan trọng:

- Gọi `read/write` khi chưa kết nối gây `NotYetConnectedException`.
- Gọi `connect` trong lúc kết nối đang pending gây `ConnectionPendingException`.
- Gọi connect khi đã kết nối gây `AlreadyConnectedException`.
- `getRemoteAddress()` giúp xác định remote endpoint khi đã kết nối, nhưng **không biến kiểm tra trạng thái thành bảo đảm tránh race** nếu thread khác đang close.
- `Future<Void>.get()` trả `null` khi connect thành công; với callback, `completed(null, attachment)` là bình thường.
- Connection refused, địa chỉ không hợp lệ, network unavailable hoặc lỗi security có thể xảy ra; không nuốt lỗi rồi thử read trên một channel đã hỏng.
- Đừng nghĩ socket connect thành công đồng nghĩa dịch vụ ứng dụng đã xác thực hoặc sẵn sàng giao dịch. TCP handshake và application protocol handshake là hai tầng khác nhau.

### 4.1. Future connect đơn giản

~~~java
try (AsynchronousSocketChannel socket =
        AsynchronousSocketChannel.open()) {
    Future<Void> result = socket.connect(remote);
    result.get(5, TimeUnit.SECONDS); // Thành công trả null.
    // Chỉ từ đây mới bắt đầu read/write.
}
~~~

Đây là **đoạn minh họa**, `SocketAddress remote` phải xác định trước và cần xử lý `IOException`, `InterruptedException`, `ExecutionException`, `TimeoutException`. **Chú ý** timeout trên `get` chỉ giới hạn thời gian caller đợi, không tự đặt một socket connect timeout với semantics chung cho mọi provider. Nếu hết thời gian mà connection còn pending, phải có chính sách dừng/close/cancel rõ ràng.

### 4.2. Callback connect và attachment

~~~java
CompletableFuture<Void> connected = new CompletableFuture<>();

socket.connect(remote, connected,
        new CompletionHandler<Void, CompletableFuture<Void>>() {
            @Override
            public void completed(Void ignored,
                                  CompletableFuture<Void> promise) {
                promise.complete(null);
            }
            @Override
            public void failed(Throwable error,
                               CompletableFuture<Void> promise) {
                promise.completeExceptionally(error);
            }
        });
~~~

Đây là **adapter minh họa**. `CompletionHandler` làm việc quan trọng: báo kết nối thành công/thất bại chính xác một lần cho promise. `CompletableFuture` do **ứng dụng tự tạo**, không phải `connect` callback trả Future.

Khi triển khai server, sau khi connect thành công hãy truyền dữ liệu hoặc gửi thông điệp bắt tay của protocol; đừng làm việc nặng ngay trong completion thread. Callback có thể chạy từ pool của channel, nên nếu chặn lâu có thể ảnh hưởng tới những kết nối khác.

## 5. Hoàn tất read/write: TCP là byte stream, không phải message stream

TCP **không tự lưu ranh giới thông điệp của các lần write**. Một lần phía gửi gọi `write("ABCDEF")` có thể được phía nhận thấy thành:

~~~text
read lần 1: "AB"
read lần 2: "CD"
read lần 3: "EF"
~~~

hoặc đọc toàn bộ 6 bytes cùng một lần, tùy buffer, network stack và timing. Sự tách/gộp này là hành vi đúng của TCP.

Một callback `completed(2, request)` với buffer capacity 6 không có nghĩa message chỉ có 2 bytes. Nó báo **operation vừa nhận được 2 bytes**; còn bao nhiêu bytes thuộc message phải được protocol/application biết.

### 5.1. Khi nào biết đã đọc đủ?

Có ba chiến lược thường dùng:

1. **Độ dài cố định**: đã biết body đúng 4 bytes, đọc cho đến khi buffer chứa 4 bytes.
2. **Length-prefix protocol**: đọc header có độ dài cố định, phân tích N, giới hạn N rồi đọc đủ N bytes. Phải chống length quá lớn/malicious.
3. **Delimiter protocol**: đọc cho tới `\\n` hoặc delimiter được định nghĩa, xử lý trường hợp delimiter chia qua nhiều buffers và giới hạn kích thước.

Trong demo phần 10, giao thức thử **cố định**: client gửi `ping` đúng 4 bytes, server trả `pong!` đúng 5 bytes. Điều này giúp viết hàm `readFully` có điểm kết thúc rõ ràng.

### 5.2. Partial write và ByteBuffer

Một lần write trả `count` bytes đã chuyển vào socket layer. Nếu `buffer.hasRemaining()` vẫn true, hãy submit write tiếp theo **sau khi completion của operation hiện tại**.

~~~java
int total = 0;
while (source.hasRemaining()) {
    int count = socket.write(source).get(5, TimeUnit.SECONDS);
    if (count <= 0) {
        throw new IOException("Write made no progress");
    }
    total += count;
}
~~~

Đây là **đoạn minh họa**. Với source buffer còn dữ liệu, count 0 không phải lỗi protocol tự thân, nhưng demo chọn fail-fast để tránh busy loop. Ứng dụng production có thể retry với backoff, deadline và giới hạn số lần không tiến triển.

### 5.3. Partial read và end-of-stream

~~~java
int total = 0;
while (target.hasRemaining()) {
    int count = socket.read(target).get(5, TimeUnit.SECONDS);
    if (count == -1) {
        throw new IOException("EOF before complete message");
    }
    if (count == 0) {
        throw new IOException("Read made no progress");
    }
    total += count;
}
~~~

Đây là **đoạn minh họa** cho protocol yêu cầu đúng N bytes. Nếu peer đóng nửa gửi trước khi đủ N, `-1` là EOF **không phải IOException của socket**; code chủ động biến thành **lỗi protocol: message bị cắt ngắn**. Với protocol cho phép read-until-EOF, xử lý `-1` thành kết thúc hợp lệ thay vì ném lỗi.

### 5.4. EOF chính là `-1`, không phải `0`

| Read result | Ý nghĩa |
| --- | --- |
| `count > 0` | Nhận được một số byte |
| `count == 0` | Operation chưa chuyển byte nào; không kết luận EOF |
| `count == -1` | Không còn dữ liệu do end-of-stream |
| Exception | I/O thất bại, operation bị hủy, timeout hoặc channel/connection không hợp lệ |

**`ByteBuffer.allocate(0)`** hoặc buffer không còn `remaining()` có thể làm một read hoàn tất tức thì với `0`, vì không có chỗ để nhận bytes. Không dùng buffer rỗng để kiểm tra remote peer đã đóng chưa.

## 6. Chỉ một read và một write pending trên mỗi socket

Đặc trưng riêng của `AsynchronousSocketChannel` so với nhiều cách đọc/ghi file:

- Có thể có **một read** đang pending.
- Có thể có **một write** đang pending.
- **Một read và một write** được phép pending đồng thời trên cùng connected channel.
- Submit **read thứ hai** khi read trước chưa hoàn tất → `ReadPendingException`.
- Submit **write thứ hai** khi write trước chưa hoàn tất → `WritePendingException`.

~~~java
Future<Integer> reading = socket.read(readBuffer);
Future<Integer> writing = socket.write(writeBuffer);
~~~

Đây là **minh họa khả dĩ** khi socket đã connected và hai buffers riêng; full-duplex TCP cho phép read/write khác chiều.

~~~java
Future<Integer> first = socket.read(bufferA);
Future<Integer> second = socket.read(bufferB); // ReadPendingException nếu first pending.
~~~

Đây là **phản ví dụ**: nếu `first` chưa completed, không submit second. Khi hai operations read nối tiếp có thể hoàn tất cực nhanh, không dùng ví dụ này làm unit test chắc chắn phải ném exception — cần kiểm soát trạng thái pending. **Cách đúng là chờ completion rồi mới phát read kế tiếp.**

Không dùng chung một `ByteBuffer` cho hai I/O đang pending, kể cả một read và một write. Javadoc cảnh báo buffer không an toàn khi nhiều thao tác bất đồng bộ dùng đồng thời; hơn nữa Java memory visibility và position/limit cần có ownership rõ ràng.

### 6.1. ByteBuffer là vùng bytes, không phải String

Để gửi:

~~~java
ByteBuffer send = ByteBuffer.wrap(
        "ping".getBytes(StandardCharsets.UTF_8));
~~~

Để nhận:

~~~java
ByteBuffer receive = ByteBuffer.allocate(4);
// Sau khi read đầy đủ và hoàn tất:
receive.flip();
String text = StandardCharsets.UTF_8.decode(receive).toString();
~~~

Đây là các ví dụ minh họa. `flip()` chuyển buffer vừa nhận bytes sang chế độ đọc: limit thành vị trí trước, position về 0. **Không flip/read/clear buffer khi I/O đang pending.**

Với tiếng Việt hoặc Unicode ngoài ASCII, một ký tự UTF-8 có thể chiếm nhiều bytes; nếu đọc stream thành chunks, hãy dùng `CharsetDecoder` hoặc buffer tích lũy hợp lý để không phá một ký tự nhiều byte tại ranh giới chunk.

## 7. Future: kết quả, lỗi và thời điểm chờ

| Operation | `Future` | `get()` thành công |
| --- | --- | --- |
| `connect(remote)` | `Future<Void>` | `null` |
| `read(dst)` | `Future<Integer>` | số bytes, hoặc `-1` EOF |
| `write(src)` | `Future<Integer>` | số bytes đã ghi |
| `server.accept()` | `Future<AsynchronousSocketChannel>` | connected socket mới |

`Future.get()` có thể **block** caller, dù lời gọi `connect/read/write` khởi tạo bất đồng bộ. Để kiểm tra bằng deadline:

~~~java
try {
    int n = pendingRead.get(5, TimeUnit.SECONDS);
    // Thành công: n có thể -1, 0 hoặc dương.
} catch (TimeoutException ex) {
    // ĐÃ HẾT THỜI GIAN CHỜ, I/O CÓ THỂ VẪN PENDING.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    // Báo lỗi thật của I/O, ví dụ AsynchronousCloseException.
} catch (CancellationException ex) {
    // Future bị hủy.
}
~~~

Đoạn minh họa yêu cầu import các loại exception. Đừng bắt `Exception` rồi im lặng coi socket đã nhận/ghi đủ bytes.

**`isDone()` không đồng nghĩa thành công**: nó cũng true khi Future bị hủy hoặc thất bại. `isCancelled()` cho biết trạng thái hủy, **không đảm bảo write chưa thay đổi gì ở network**. Muốn biết outcome, phải xử lý `get()`/exception theo contract.

### 7.1. Future không tự là CompletableFuture

`connect(remote)` trả `Future<Void>`, `read(dst)` và `write(src)` trả `Future<Integer>`. **Không ép kiểu** chúng sang `CompletableFuture` rồi giả định có `thenCompose`, vì interface API không hứa type thực tế.

Nếu ứng dụng muốn composition dựa trên callbacks, tạo `CompletableFuture` adapter riêng: callback `completed` gọi `complete`, callback `failed` gọi `completeExceptionally`, như chương trình phần 10.

## 8. CompletionHandler: tách kết quả khỏi caller

Dạng tổng quát:

~~~java
<A> void connect(SocketAddress remote, A attachment,
                 CompletionHandler<Void, ? super A> handler);

<A> void read(ByteBuffer dst, A attachment,
              CompletionHandler<Integer, ? super A> handler);

<A> void write(ByteBuffer src, A attachment,
               CompletionHandler<Integer, ? super A> handler);
~~~

Đây là **chữ ký rút gọn để học**, không phải các phương thức bạn tự định nghĩa. `A` là kiểu *attachment* — context được đưa ngược lại cho callback.

Một handler kết quả:

~~~java
socket.read(buffer, request,
        new CompletionHandler<Integer, Request>() {
            @Override
            public void completed(Integer count, Request req) {
                // count > 0: thêm bytes vào bộ đệm protocol.
                // count == -1: EOF.
                // Nếu cần, submit read kế tiếp SAU completion hiện tại.
            }

            @Override
            public void failed(Throwable error, Request req) {
                // Báo lỗi và dọn state/connection theo policy.
            }
        });
~~~

Đoạn minh họa cần `Request` là kiểu ngữ cảnh riêng; không phải class JDK. **Không gửi I/O tiếp theo với cùng buffer trước khi lần trước hoàn tất.** Và không block lâu/đợi Future khác ngay trong handler của pool bất đồng bộ nếu điều đó có thể cản trở các completion khác.

### 8.1. Attachment cần lưu gì?

Một state object thường chứa:

- `ByteBuffer` của đúng request.
- Độ dài logical message mong muốn và số bytes đã nhận/ghi.
- ID request, authentication/session state, log correlation ID.
- Kết quả ứng dụng sẽ thông báo cho caller.
- Deadline/cancellation state và cờ xác định liệu request đã hoàn tất chưa.

Callback có thể chạy trên thread khác với caller. Attachment mutable **không tự thread-safe** chỉ vì được truyền cho `CompletionHandler`. Nếu shared state, thiết kế synchronization/serial executor hoặc dùng immutable messages.

### 8.2. Handler thất bại phải được quan sát

`failed(Throwable error,A attachment)` không phải chỉ để ghi `printStackTrace()` rồi bỏ mặc pending business request. Nó phải gửi outcome cho hệ điều phối, dọn bộ đệm, hủy những yêu cầu phụ thuộc và có chính sách close/retry.

Đặc biệt, **connect thất bại đóng channel** theo contract. Không nên retry lại trên chính channel đã thất bại; nếu muốn reconnect, tạo channel mới và xử lý backoff/giới hạn retries.

## 9. Hai loại timeout rất khác nhau

### 9.1. Timeout của Future.get

~~~java
int n = socket.read(buffer).get(5, TimeUnit.SECONDS);
~~~

Nếu quá 5 giây, `get` ném `TimeoutException` vì **caller không chờ lâu hơn**. Nó **không tự hủy read đang pending**, và không cho phép dùng buffer lại tùy tiện. Một read khác lúc này có thể ném `ReadPendingException`.

### 9.2. Timeout của chính read/write operation

`AsynchronousSocketChannel` còn định nghĩa overload:

~~~java
socket.read(buffer, 5L, TimeUnit.SECONDS, attachment, handler);
socket.write(buffer, 5L, TimeUnit.SECONDS, attachment, handler);
~~~

Đây là ví dụ minh họa riêng. Nếu timeout thực xảy ra trước completion, handler nhận `failed` với `InterruptedByTimeoutException`. Theo Javadoc Java 21:

- Timeout có thể khiến channel hoặc kết nối ở trạng thái **không nhất quán**.
- Nếu provider không thể bảo đảm bytes chưa được đọc/ghi, các lần read/write tương ứng sau đó có thể ném runtime exception không được định danh cụ thể.
- Trạng thái của `ByteBuffer` liên quan operation **không được xác định** sau timeout; nên loại bỏ buffer đó hoặc xử lý thật cẩn trọng. Không reset position và gửi lại như chưa có bytes nào chuyển.
- Timeout truyền vào `<= 0` theo overload này mang nghĩa **không timeout**, chứ không có nghĩa “không chờ”.

**Phân biệt:** `TimeoutException` từ Future.get là **hết thời gian đợi của caller**; `InterruptedByTimeoutException` trong `CompletionHandler.failed` là **timeout của I/O operation**. Đây không phải cùng một tình trạng hay cùng các bảo đảm về buffer.

### 9.3. Cancellation, close và timeouts

Javadoc `AsynchronousChannel` mô tả cancellation với `Future.cancel` là implementation-dependent đối với I/O thực. `cancel(true)` có thể khiến channel bị đóng để ngắt thao tác; buffer có thể bị ảnh hưởng và bytes có thể đã chuyển một phần. Không coi cancel là rollback.

`channel.close()` làm outstanding operations bị kết thúc theo contract, thường lỗi `AsynchronousCloseException`. Sau khi channel đóng, các thao tác mới có thể báo `ClosedChannelException` hoặc lỗi tương ứng.

**Nguyên tắc:** khi gặp timeout/cancel/close, không tự coi stream ở trạng thái ban đầu. Phải đánh giá trạng thái kết nối và tầng protocol, dọn những request phụ thuộc, tạo kết nối mới nếu cần.

## 10. Chương trình Java 21 hoàn chỉnh — loopback, connect, read, write, EOF

Để bài học có stdout xác minh được nhưng **không gọi ra Internet** hay phụ thuộc máy chủ bên ngoài, chương trình tạo cả server và client trong **cùng tiến trình**:

1. Server `AsynchronousServerSocketChannel.open().bind(...)` trên `InetAddress.getLoopbackAddress()`, port `0` (hệ điều hành cấp port trống).
2. Server gọi `accept()`, nhận `Future<AsynchronousSocketChannel>`.
3. Client gọi `connect(...)` với `CompletionHandler<Void,CompletableFuture<Void>>`; main đợi promise có timeout và xác nhận kết nối thành công.
4. Server lấy connected socket qua `accepted.get(...)`.
5. Client gửi `ping` bằng **Future write**; server đọc 4 bytes bằng **Future read**.
6. Server gửi `pong!` bằng **CompletionHandler write**, client đọc 5 bytes bằng **CompletionHandler read**.
7. Hai bên lần lượt `shutdownOutput()`, đầu bên kia đọc nhận `-1` để minh họa EOF khi half-close.
8. Cả listener, client và accepted peer được đóng bằng **try-with-resources**.

Một request dùng **buffer riêng**; helper gửi/nhận đầy đủ xử lý **partial completion**. Chương trình không dùng sleep/timing đoán kết quả, không in port ngẫu nhiên và không dùng server thật từ Internet.

Tạo file `src/main/java/demo/AsyncConnectReadWriteExample.java`:

~~~java
package demo;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class AsyncConnectReadWriteExample {
    private AsyncConnectReadWriteExample() {}

    static int writeAllWithFuture(AsynchronousSocketChannel channel,
                                  ByteBuffer source) throws Exception {
        int total = 0;
        while (source.hasRemaining()) {
            int count = channel.write(source).get(5, TimeUnit.SECONDS);
            if (count <= 0) {
                throw new IOException("Write made no progress");
            }
            total += count;
        }
        return total;
    }

    static int readFullyWithFuture(AsynchronousSocketChannel channel,
                                   ByteBuffer target) throws Exception {
        int total = 0;
        while (target.hasRemaining()) {
            int count = channel.read(target).get(5, TimeUnit.SECONDS);
            if (count == -1) {
                throw new IOException("EOF before complete message");
            }
            if (count == 0) {
                throw new IOException("Read made no progress");
            }
            total += count;
        }
        return total;
    }

    private static final class Transfer {
        final ByteBuffer buffer;
        final CompletableFuture<Integer> completion = new CompletableFuture<>();
        int total;

        Transfer(ByteBuffer buffer) {
            this.buffer = buffer;
        }
    }

    static CompletableFuture<Integer> withHandler(
            AsynchronousSocketChannel channel, ByteBuffer buffer,
            boolean writing) {
        Transfer state = new Transfer(buffer);
        if (!buffer.hasRemaining()) {
            state.completion.complete(0);
            return state.completion;
        }

        final class Handler implements CompletionHandler<Integer, Transfer> {
            void submit(Transfer request) {
                try {
                    if (writing) {
                        channel.write(request.buffer, request, this);
                    } else {
                        channel.read(request.buffer, request, this);
                    }
                } catch (RuntimeException error) {
                    request.completion.completeExceptionally(error);
                }
            }

            @Override
            public void completed(Integer count, Transfer request) {
                if (count == null || count <= 0) {
                    failed(new IOException("EOF or no I/O progress"), request);
                    return;
                }
                request.total += count;
                if (request.buffer.hasRemaining()) {
                    submit(request);
                } else {
                    request.completion.complete(request.total);
                }
            }

            @Override
            public void failed(Throwable error, Transfer request) {
                request.completion.completeExceptionally(error);
            }
        }

        new Handler().submit(state);
        return state.completion;
    }

    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                        AsynchronousServerSocketChannel.open().bind(
                                new InetSocketAddress(
                                        InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client =
                        AsynchronousSocketChannel.open()) {

            Future<AsynchronousSocketChannel> accepted = server.accept();
            CompletableFuture<Void> connected = new CompletableFuture<>();

            client.connect(server.getLocalAddress(), connected,
                    new CompletionHandler<Void, CompletableFuture<Void>>() {
                        @Override
                        public void completed(Void value,
                                              CompletableFuture<Void> promise) {
                            promise.complete(null);
                        }

                        @Override
                        public void failed(Throwable error,
                                           CompletableFuture<Void> promise) {
                            promise.completeExceptionally(error);
                        }
                    });

            connected.get(5, TimeUnit.SECONDS);
            System.out.println("connect-callback-completed=true");

            try (AsynchronousSocketChannel peer =
                    accepted.get(5, TimeUnit.SECONDS)) {
                System.out.println("accepted-open=" + peer.isOpen());

                int futureWritten = writeAllWithFuture(client,
                        ByteBuffer.wrap("ping".getBytes(StandardCharsets.UTF_8)));
                System.out.println("future-written=" + futureWritten);

                ByteBuffer receivedOnServer = ByteBuffer.allocate(4);
                System.out.println("future-read=" +
                        readFullyWithFuture(peer, receivedOnServer));
                receivedOnServer.flip();
                System.out.println("server-received=" +
                        StandardCharsets.UTF_8.decode(receivedOnServer));

                int callbackWritten = withHandler(peer,
                        ByteBuffer.wrap("pong!".getBytes(StandardCharsets.UTF_8)),
                        true).get(5, TimeUnit.SECONDS);
                System.out.println("callback-written=" + callbackWritten);

                ByteBuffer receivedOnClient = ByteBuffer.allocate(5);
                int callbackRead = withHandler(client, receivedOnClient, false)
                        .get(5, TimeUnit.SECONDS);
                receivedOnClient.flip();
                System.out.println("callback-read=" + callbackRead);
                System.out.println("client-received=" +
                        StandardCharsets.UTF_8.decode(receivedOnClient));

                peer.shutdownOutput();
                int clientEof = client.read(ByteBuffer.allocate(1))
                        .get(5, TimeUnit.SECONDS);
                System.out.println("client-eof=" + clientEof);

                client.shutdownOutput();
                int serverEof = peer.read(ByteBuffer.allocate(1))
                        .get(5, TimeUnit.SECONDS);
                System.out.println("server-eof=" + serverEof);
            }
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 21** từ thư mục chứa `src/`:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/AsyncConnectReadWriteExample.java
java -cp out demo.AsyncConnectReadWriteExample
~~~

**Stdout chính xác đã kiểm thử trên Windows với loopback TCP:**

~~~text
connect-callback-completed=true
accepted-open=true
future-written=4
future-read=4
server-received=ping
callback-written=5
callback-read=5
client-received=pong!
client-eof=-1
server-eof=-1
~~~

### 10.1. Giải thích từng kết quả

- `connect-callback-completed=true`: handler connect gọi `complete(null)` lên promise; main chỉ in sau `get(...)` thành công.
- `accepted-open=true`: server lấy connected `AsynchronousSocketChannel` từ Future `accept`; peer đang mở tại thời điểm kiểm tra.
- `future-written=4`: client đã truyền 4 bytes của `"ping"` bằng Future write, có vòng lặp khi write từng phần.
- `future-read=4`: server nhận đủ 4 bytes vào một buffer trước khi decode.
- `server-received=ping`: server thấy nội dung đúng qua TCP stream.
- `callback-written=5`: callback write phía server gửi đủ 5 bytes của `"pong!"`.
- `callback-read=5`: callback read phía client nhận đủ 5 bytes.
- `client-received=pong!`: sau `flip()` và decode UTF-8, dữ liệu nhận đúng.
- `client-eof=-1`: sau `peer.shutdownOutput()` và sau khi đã nhận đủ response, client đọc tiếp sẽ nhận EOF.
- `server-eof=-1`: sau `client.shutdownOutput()`, server đọc thêm nhận EOF.

Các dòng phản ánh **kết quả đã quan sát trong môi trường test**, không phải cam kết rằng TCP mọi nơi luôn hoàn thành một read/write trong thời gian cố định. Vì vậy helper dùng `Future.get(5,SECONDS)` hoặc promise.get để kết thúc bài test khi peer không đáp ứng.

### 10.2. Vì sao helper Future dùng vòng lặp?

`writeAllWithFuture` gọi một write, đợi Future, tăng tổng và tiếp tục nếu buffer vẫn có bytes. Nó không submit hai writes pending trên cùng socket, nên không vi phạm `WritePendingException`.

`readFullyWithFuture` dùng buffer capacity N được protocol test định nghĩa, đợi từng lần read, tăng tổng, và chỉ trả khi đủ N. EOF trước khi đủ được chuyển thành `IOException` chủ động báo **message không hoàn chỉnh**. Trong TCP nói chung, phải có **cách xác định độ dài message trước** mới biết thế nào là “đủ”.

### 10.3. Vì sao helper CompletionHandler dùng `Transfer`?

`Transfer` giữ một `ByteBuffer` và promise riêng của **một logical transfer**. Mỗi lần callback:

1. `completed(count, request)` nhận số bytes của operation vừa xong.
2. Nếu count dương, cập nhật total.
3. Nếu buffer còn data/space, gọi `submit(request)` **sau completion** để gửi/nhận lần tiếp theo.
4. Nếu buffer đã hết remaining, hoàn tất promise với tổng bytes.
5. Nếu `failed` hoặc không có tiến triển, promise thất bại qua `completeExceptionally`.

Chương trình chọn chính sách **fail-fast khi count == 0 hoặc đọc EOF sớm** cho các thông điệp N bytes đã biết, không triển khai retry/backoff của một server dùng tải lớn. Đây là điểm **cần phân biệt demo với production**.

`CompletableFuture` ở main là adapter để chờ kết quả theo thứ tự cố định trong một bài thử. Thực tế handler overload của `AsynchronousSocketChannel` vẫn trả `void`; adapter là phần do ứng dụng bổ sung để dễ điều phối.

### 10.4. Half-close

`peer.shutdownOutput()` chỉ ngừng **gửi** trên hướng của peer tới client, không nhất thiết đóng ngay cả socket ở hai chiều. Sau khi bên nhận tiêu thụ hết bytes đã gửi, read tiếp sẽ trả `-1` khi nhận EOF.

`shutdownInput()` và `shutdownOutput()` khác `close()`: chúng liên quan từng hướng truyền/nhận. Ứng dụng phải định nghĩa protocol khi nào gửi kết thúc, khi nào xử lý ACK và khi nào đóng. Không dùng EOF làm dấu phân cách message nếu muốn giữ một kết nối lâu dài phục vụ nhiều request.

## 11. Timeout và cancellation khi vận hành thực

Để không treo vô hạn khi peer không trả lời:

- Có **deadline tổng** của request/session.
- Hạn chế số I/O outstanding và memory/buffer budget.
- Dùng `get(timeout)` khi chờ Future, nhưng biết I/O có thể còn pending.
- Khi dùng overload I/O timeout, xử lý `InterruptedByTimeoutException` và **không tự tái dùng buffer ở trạng thái không xác định**.
- Khi callback/Promise báo lỗi, dọn hoặc đóng connection theo policy; không retry trên socket connect đã thất bại.
- Nếu có retry, phải biết request có **idempotent** không; gửi lại gói thanh toán hoặc ghi dữ liệu khi kết quả lần trước không rõ có thể gây side effect hai lần.
- Cancellation/close không bảo đảm undo bytes đã gửi; định danh request và ACK ở **tầng protocol** mới xử lý được trạng thái nghiệp vụ.

### 11.1. TCP backpressure

Một send quá nhanh có thể khiến socket write hoàn tất từng phần hoặc chậm vì peer đọc chậm. Đừng tạo **hàng trăm write pending cùng lúc trên một connection**; `AsynchronousSocketChannel` giới hạn một write outstanding. Nên duy trì **per-connection outbound queue**; submit write mới **sau khi write cũ hoàn tất**, tôn trọng backpressure.

Tương tự, chỉ một read pending; khi nhận đủ một frame, chuyển dữ liệu tới worker xử lý và submit read tiếp khi memory budget cho phép. Nếu worker cần thời gian, giữ queue bounded và báo lỗi/đóng theo chính sách thay vì tích vô hạn messages.

### 11.2. Readiness không phải TCP completion

Asynchronous I/O completion là **hoàn tất operation được gọi**, không phải `Selector` readiness. `Selector` của non-blocking `SocketChannel` nói “có thể đọc/ghi” để code tự gọi thao tác; `CompletionHandler` của `AsynchronousSocketChannel` báo số bytes đã được operation truyền.

Không trộn kiểu callback completion với mã select loop của `SelectionKey` rồi nghĩ chúng đồng nghĩa. Cả hai đều là API Java hiện đại, nhưng có mô hình điều phối khác nhau.

## 12. Lỗi, exception và vòng đời

| Tình huống | Biểu hiện | Hướng xử lý |
| --- | --- | --- |
| Read/write trước connect thành công | `NotYetConnectedException` | Chờ connect completed |
| Connect lại khi đã connected | `AlreadyConnectedException` | Không mở lại kết nối trên cùng channel |
| Connect mới trong khi connect đang pending | `ConnectionPendingException` | Chờ outcome hiện tại |
| Accept khi server chưa bind | `NotYetBoundException` | `bind()` trước |
| Hai accept outstanding cùng listener | `AcceptPendingException` | Submit accept tiếp theo khi lượt trước hoàn tất |
| Hai read outstanding cùng socket | `ReadPendingException` | Chờ read trước hoàn tất |
| Hai write outstanding cùng socket | `WritePendingException` | Tuần tự hóa outbound queue |
| Địa chỉ không phân giải | `UnresolvedAddressException` | Xác minh DNS/địa chỉ |
| Kiểu địa chỉ không được hỗ trợ | `UnsupportedAddressTypeException` | Dùng đúng SocketAddress/provider |
| Connect bị từ chối | I/O failure như `ConnectException` trong callback/`ExecutionException.getCause()` | Báo lỗi, đóng kết nối, retry có backoff nếu nghiệp vụ cho phép |
| Socket bị đóng trong khi chờ | `AsynchronousCloseException` hoặc lỗi channel tương ứng | Hoàn tất request thất bại, cleanup |
| Timeout của Future.get | `TimeoutException` | Không coi I/O đã tự hủy |
| Timeout của overload read/write | `InterruptedByTimeoutException` trong handler | Xử lý buffer/channel state không xác định |
| Future bị cancel | `CancellationException` từ `get` | Không coi bytes chưa truyền |
| Thread chờ bị interrupt | `InterruptedException` | Truyền lỗi lên hoặc restore interrupt và dừng |
| Read trả `-1` | EOF, không phải exception | Xử lý đóng hoặc message thiếu theo protocol |
| Read/write trả `0` | Không có tiến triển | Tránh spin, có giới hạn/backoff |
| Channel group đã shutdown | `ShutdownChannelGroupException` | Không submit lên group đã dừng |
| Peer biến mất khi ứng dụng đang ghi | Có thể I/O failure, EOF ở read hoặc trạng thái nửa đóng | Hủy request phụ thuộc và dọn socket |

Không nên bắt mọi lỗi thành “peer disconnected” vì một số lỗi là **bug điều phối** (hai read pending, buffer misuse, connect chưa xong), còn lỗi khác là môi trường (timeout, refused connection).

### 12.1. Retry chỉ sau khi hiểu tình trạng lần trước

Nếu write timeout, ứng dụng **không chắc** bao nhiêu byte đã được peer nhận và xử lý. Gửi lại toàn bộ logical request trên connection mới có thể tạo duplicate. Với protocol quan trọng, cần request ID, deduplication/idempotency, ACK hoặc transaction ở tầng ứng dụng. `Future` và `CompletionHandler` chỉ cho **I/O outcome**, không cho outcome của nghiệp vụ tại peer.

### 12.2. Socket options không thay cho protocol

`AsynchronousSocketChannel.setOption(...)` hỗ trợ các socket options như `TCP_NODELAY`, `SO_KEEPALIVE`, `SO_SNDBUF`, `SO_RCVBUF` khi provider hỗ trợ. Chúng có thể ảnh hưởng hành vi truyền dữ liệu hoặc phát hiện kết nối chết ở tầng OS nhưng **không tạo message framing, retry chính xác hay bảo mật TLS**.

Nếu kết nối đi qua mạng không tin cậy, phải có giải pháp mã hóa/xác thực phù hợp (TLS hoặc giao thức đã bảo vệ); TCP async bản thân **không tự mã hóa**. Không dùng ví dụ loopback làm bằng chứng sẵn sàng cho Internet.

## 13. Cách phát triển thành một client/server nhiều kết nối

Một thiết kế ứng dụng:

~~~text
Listener accept()
    |
    +-- accepted channel A --> Session A
    |                         read pending <= 1
    |                         write pending <= 1
    |                         inbound frame parser
    |                         bounded outbound queue
    |
    +-- accepted channel B --> Session B
                              ...
 
Session:
    CONNECTED
        |
        +-- read completed(count) -> decode frame -> enqueue work
        |
        +-- write completed(count) -> flush remaining -> next message
        |
        +-- failed(error)/EOF -> close and cleanup
~~~

Khi server muốn nhận nhiều client, sau khi một `accept` completes, listener có thể submit **accept tiếp theo** và song song xử lý peer mới. Nhưng không gọi hai `accept()` trên cùng listener khi accept đầu vẫn pending, nếu không có thể gặp `AcceptPendingException`.

### 13.1. Một session nên có state cụ thể

- `CONNECTING`: chưa được phép read/write.
- `CONNECTED`: một read và một write tối đa đang pending; protocol xác định frame.
- `CLOSING`: ngừng nhận jobs mới, giải quyết outstanding I/O theo chính sách.
- `CLOSED`: đóng channel, thông báo các requests chưa hoàn tất.

Một session không nên dùng nhiều Boolean rời rạc không đồng bộ khiến callback đến trễ mở lại một request đã bị hủy. Có thể dùng single-threaded state machine/serial executor hoặc các primitives thread-safe.

### 13.2. Xác thực, kích thước message và hạn chế tài nguyên

Trước khi tin vào một length-prefix nhận từ network, kiểm tra nó thuộc khoảng hợp lệ, tránh cấp `ByteBuffer.allocate(Integer.MAX_VALUE)` theo dữ liệu do peer kiểm soát. Giới hạn frame size, tổng bytes, số connections, worker queue depth, deadline và tốc độ nhận/gửi.

Nếu client không hoàn thành header hoặc gửi dữ liệu rất chậm, dùng timeout phù hợp và quota; đừng để mỗi client giữ vô hạn một buffer/connection. **Async socket không tự giải quyết DoS hay memory growth.**

### 13.3. Không suy ra application ACK từ Future write

Future write count dương nghĩa **operation đã đưa bytes vào đường truyền** theo contract, không chứng minh peer đã nhận đủ/giải mã/xử lý. Muốn đảm bảo nghiệp vụ đã xử lý thành công, peer phải gửi một **ACK có định nghĩa trong protocol**, và client phải đọc/kiểm tra ACK đó.

## 14. Sai lầm thường gặp

**Sai lầm 1 — “Connect() trả Future<Integer> giống read/write.”**  
Không. Connect trả `Future<Void>`, thành công `get()` trả `null`; callback dùng `CompletionHandler<Void,A>`.

**Sai lầm 2 — “Ngay sau connect(...) có thể read/write chắc chắn được.”**  
Không. Connect là bất đồng bộ; cần chờ thành công hoặc xử lý `completed`. Nếu chưa connected, `NotYetConnectedException`.

**Sai lầm 3 — “Callback connect completed(null) là thất bại.”**  
Không. `Void` không có giá trị hữu ích, nên `null` là bình thường.

**Sai lầm 4 — “Một write tương ứng một read cùng kích thước.”**  
Không. TCP là byte stream; frame phải do ứng dụng xác định.

**Sai lầm 5 — “read() trả 0 nghĩa socket đã đóng.”**  
Không. EOF là `-1`. Read 0 chỉ là chưa chuyển byte.

**Sai lầm 6 — “Future.get(timeout) đã hủy I/O khi quá hạn.”**  
Không. Timeout của caller và timeout của operation là khác nhau.

**Sai lầm 7 — “Có thể gọi hai read chồng nhau để tăng tốc.”**  
Không đối với `AsynchronousSocketChannel`; có tối đa một read và một write outstanding.

**Sai lầm 8 — “Gọi hai write cùng lúc để tăng throughput.”**  
Không trên cùng async socket; `WritePendingException` có thể xảy ra. Xếp queue theo phiên giao tiếp.

**Sai lầm 9 — “Một ByteBuffer dùng chung nhiều request không sao.”**  
Không. Buffer ownership phải rõ ràng khi bất đồng bộ.

**Sai lầm 10 — “write completed đồng nghĩa peer đã xử lý request.”**  
Không. Cần ACK ở tầng ứng dụng.

**Sai lầm 11 — “read EOF trước N byte có thể coi như message đầy đủ.”**  
Không nếu protocol yêu cầu đủ N byte. Bài test ném lỗi “EOF before complete message”.

**Sai lầm 12 — “Socket async tự mã hóa dữ liệu.”**  
Không. TCP không tự có TLS/application security.

**Sai lầm 13 — “Hai callback luôn chạy đúng thứ tự gửi yêu cầu.”**  
Không có bảo đảm thứ tự completion tổng thể; phải điều phối state.

**Sai lầm 14 — “Timeout của read/write operation không ảnh hưởng buffer.”**  
Sai. Javadoc cảnh báo trạng thái buffer sau `InterruptedByTimeoutException` có thể không xác định và channel ở trạng thái lỗi.

**Sai lầm 15 — “cancel(true) undo dữ liệu đã gửi.”**  
Không. I/O thực có thể đã truyền một phần; cancellation không tạo rollback.

**Sai lầm 16 — “Accept trả về một boolean cho biết kết nối đã đến.”**  
Không. Future accept trả `AsynchronousSocketChannel` đã connected; callback nhận socket.

**Sai lầm 17 — “Đóng listener cũng là xử lý mọi kết nối đã accept xong.”**  
Accepted socket có vòng đời riêng; phải sở hữu và đóng từng peer đúng cách.

**Sai lầm 18 — “Có event kết nối là có thể cấp phát message buffer theo số client gửi mà không giới hạn.”**  
Không. Dữ liệu mạng không tin cậy; phải giới hạn kích thước, số kết nối và queues.

## 15. Câu hỏi và bài tập tự kiểm tra

**Câu 1.** `client.connect(addr)` trả gì?  
**Đáp án:** `Future<Void>`; `get()` trả `null` khi kết nối thành công.

**Câu 2.** `client.connect(addr, request, handler)` trả gì?  
**Đáp án:** `void`; handler dùng `CompletionHandler<Void,A>` để nhận thành công hoặc lỗi.

**Câu 3.** Vì sao không dùng `client.read(...)` ngay khi vừa gọi connect?  
**Đáp án:** Connect còn có thể pending; phải đợi connect complete. Trước đó, `NotYetConnectedException` có thể được ném.

**Câu 4.** `server.accept()` trả `Future<Boolean>` hay `Future<AsynchronousSocketChannel>`?  
**Đáp án:** `Future<AsynchronousSocketChannel>`; result là connected peer channel.

**Câu 5.** Nếu read buffer còn 10 byte nhưng operation completed 4, có nghĩa thông điệp chỉ có 4 byte?  
**Đáp án:** Không. TCP không giữ ranh giới message, ứng dụng phải biết/đọc tiếp theo frame protocol.

**Câu 6.** Read trả `-1` có phải lỗi socket I/O?  
**Đáp án:** Không. Nó là EOF; có thể là kết thúc hợp lệ hoặc message bị cắt ngắn tùy protocol.

**Câu 7.** Hai read pending trên cùng `AsynchronousSocketChannel` được phép không?  
**Đáp án:** Không; `ReadPendingException` nếu read đầu chưa hoàn tất. Một read và một write khác chiều có thể pending đồng thời.

**Câu 8.** Trong ví dụ, vì sao client chờ `connected.get(5,SECONDS)`?  
**Đáp án:** Promise adapter chỉ hoàn tất khi callback connect gọi `completed`, giúp không submit read/write trên unconnected channel.

**Câu 9.** Vì sao server đợi `accepted.get` trước khi read?  
**Đáp án:** Để có `AsynchronousSocketChannel` mới đại diện kết nối đã được accept.

**Câu 10.** `futureWrite.get()` trả 5 có nghĩa peer đã nhận và xử lý yêu cầu dài 5 byte?  
**Đáp án:** Không. Nó báo số byte I/O write chuyển được; peer xử lý là một outcome khác cần ACK.

**Câu 11.** Sự khác nhau giữa `TimeoutException` và `InterruptedByTimeoutException`?  
**Đáp án:** `TimeoutException` ở `Future.get(timeout)` chỉ báo caller đã chờ quá lâu. `InterruptedByTimeoutException` ở handler read/write có timeout báo operation timeout và có thể làm trạng thái channel/buffer không xác định.

**Câu 12.** Với callback read có `count=0`, nên gọi EOF không?  
**Đáp án:** Không. EOF là -1. Cần policy không tiến triển, không spin vô hạn.

**Câu 13.** `shutdownOutput()` có vai trò gì?  
**Đáp án:** Chấm dứt hướng gửi của socket; peer có thể đọc tới EOF sau khi tiêu thụ các bytes còn lại, trong khi hướng đọc vẫn có thể dùng nếu chưa shutdown.

**Câu 14.** Callback có thể chạy trên thread main không?  
**Đáp án:** Không được giả định. Handler chạy theo group/pool; nếu thread khởi tạo thuộc pool và operation hoàn tất ngay, callback có thể thực hiện trực tiếp tại thread đó.

**Câu 15.** Tại sao không dùng một `ByteBuffer` cho nhiều callbacks song song?  
**Đáp án:** Bộ đệm có mutable position/limit/bytes, và contract không cho truy cập đồng thời khi I/O pending.

**Câu 16.** Khi connect thất bại, retry trên cùng channel đang thất bại được không?  
**Đáp án:** Không nên: Javadoc nêu connect thất bại thì channel bị đóng. Nếu retry theo nghiệp vụ, mở channel mới và dùng backoff.

**Câu 17.** Vì sao trong example readFully cần capacity cụ thể 4 hoặc 5?  
**Đáp án:** Vì protocol demo định nghĩa message có độ dài đó. Với real protocol phải có framing như length-prefix hoặc delimiter.

**Câu 18.** Khi write timed out, có an toàn reset buffer và gửi lại toàn bộ message ngay không?  
**Đáp án:** Không. Trạng thái ByteBuffer và lượng bytes có thể đã truyền không chắc chắn; phải xử lý request theo protocol/cancellation/reconnection và idempotency.

## 16. Checklist thực hành

- [ ] Dùng `AsynchronousSocketChannel` cho connected stream và `AsynchronousServerSocketChannel` cho accept.
- [ ] Không gọi read/write khi connect chưa hoàn tất.
- [ ] Connect Future trả `Void`, read/write trả `Integer`, accept trả connected socket.
- [ ] Có đầy đủ nhánh `completed` và `failed` khi dùng handler.
- [ ] Hiểu `Future.get()` có thể chặn; timeout của get không phải timeout operation.
- [ ] Không có hơn một pending read và một pending write trên cùng async socket.
- [ ] Buffer riêng cho mỗi pending I/O, không đổi position/limit trước completion.
- [ ] Quản lý partial read/write đến khi đủ frame theo protocol.
- [ ] Phân biệt `-1` EOF và `0` no progress.
- [ ] Không coi TCP socket là message queue có ranh giới sẵn.
- [ ] Dùng length-prefix/delimiter/fixed-length và giới hạn kích thước message.
- [ ] Theo dõi outbound queue/backpressure, không phát vô hạn pending writes.
- [ ] Không coi write-completion là application ACK.
- [ ] Nếu dùng I/O timeout handler, xử lý `InterruptedByTimeoutException`, có thể hủy buffer/channel.
- [ ] Cẩn trọng cancel/close khi request pending, không hứa rollback bytes.
- [ ] Giữ listener và từng accepted/client socket với vòng đời riêng.
- [ ] Có giới hạn kết nối, payload, queues, retry và thời gian chờ.
- [ ] Không tự coi TCP bất đồng bộ là mã hóa; thêm security thích hợp khi qua mạng không tin cậy.
- [ ] Dùng try-with-resources/shutdown group khi sở hữu group, bảo toàn tài nguyên.
- [ ] Xác nhận API trên JDK hiện đại và provider đích; không dùng kiến thức legacy.

## 17. Nguồn chính thức Java SE 21

- [AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): connect Future/handler, read/write, một read và write outstanding, timeout, shutdown, trạng thái channel.
- [AsynchronousServerSocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): bind, accept Future/handler, accepted socket, AcceptPendingException.
- [AsynchronousByteChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousByteChannel.html): count, partial reads/writes, EOF và ByteBuffer ownership.
- [AsynchronousChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousChannel.html): Future/CompletionHandler, close, cancel và pending operations.
- [CompletionHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/CompletionHandler.html): `completed`, `failed` và attachment.
- [Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): `get`, `isDone`, `cancel`, `isCancelled`.
- [CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): promise ứng dụng dùng để adapter callback.
- [ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): `wrap`, `allocate`, `hasRemaining`, `flip`, `position`.
- [AsynchronousChannelGroup](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html): group/pool và shutdown khi nhóm do ứng dụng quản lý.
- [InetSocketAddress](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetSocketAddress.html): địa chỉ IP/port, `port=0` được OS gán khi bind.

**Kết luận:** Hoàn tất `connect`, `read` và `write` trong Java NIO.2 nghĩa là nhận **outcome của từng thao tác cụ thể**: connect `Void`, read/write `Integer` hoặc lỗi trong Future/callback. Bởi TCP là **byte stream**, cần tự xử lý partial I/O, framing, EOF, buffers, callback state và backpressure. Thao tác bất đồng bộ giúp không buộc thread caller đứng đợi ngay, nhưng không thay thế quản lý lỗi, timeout, xác thực và tài nguyên.
