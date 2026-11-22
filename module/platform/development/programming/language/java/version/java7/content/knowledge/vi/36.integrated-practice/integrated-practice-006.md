# Đọc ghi tệp hoặc phục vụ kết nối bằng kênh bất đồng bộ trong Java (NIO.2)

## 1. Mục tiêu và phạm vi sử dụng

Trong ứng dụng Java, một tác vụ I/O thường cần chờ dữ liệu từ ổ đĩa hoặc socket. API **kênh bất đồng bộ (asynchronous channels)** của `java.nio.channels` cho phép **khởi tạo thao tác** rồi nhận kết quả sau, thay vì buộc luồng gọi phải chờ ngay trong phương thức `read`, `write` hoặc `accept`.

Bài thực hành tổng hợp hai trường hợp vẫn phù hợp với Java hiện đại:

- **Tệp:** `AsynchronousFileChannel` đọc/ghi từ một `Path` với **vị trí byte tường minh**.
- **Kết nối TCP:** `AsynchronousServerSocketChannel` tiếp nhận client và `AsynchronousSocketChannel` thực hiện kết nối, đọc/ghi stream bằng `CompletionHandler` hoặc `Future`.

Đây là các API NIO.2 đã có từ Java 7 và vẫn được hỗ trợ. Ví dụ biên dịch bằng **Java 17+**, chỉ dùng thư viện chuẩn JDK. Chúng minh họa cơ chế bất đồng bộ, kiểm soát buffer, xử lý partial I/O, đóng tài nguyên và giới hạn dữ liệu; không quảng bá mô hình này là cách duy nhất hoặc luôn nhanh hơn mọi giải pháp I/O khác.

**Sau bài học, bạn có thể:**

1. Phân biệt lời gọi *khởi tạo I/O bất đồng bộ* với lời gọi `Future.get()` **đợi đồng bộ**.
2. Dùng `ByteBuffer` đúng với `position`, `limit`, `flip` và `hasRemaining()`.
3. Đọc/ghi tệp theo offset, xử lý EOF và trường hợp mỗi lần truyền ít byte hơn yêu cầu.
4. Tạo TCP server loopback một client với `accept`, `read`, `write` và callback xử lý thành công/thất bại.
5. Dùng giao thức TCP có **framing** (độ dài + payload) thay vì giả định mỗi lần `read` là một message.
6. Đánh giá cancellation, timeout, backpressure, lifecycle và lựa chọn thay thế bằng virtual threads.

## 2. Hai cách nhận kết quả: Future và CompletionHandler

`AsynchronousChannel` có hai mẫu API:

~~~java
// Mẫu 1: gọi trả về Future ngay, kết quả có sau.
Future<Integer> pending = channel.read(buffer, position);
int bytesRead = pending.get(); // Đợi; luồng gọi bị block tại đây.

// Mẫu 2: callback hoàn thành hoặc thất bại.
channel.read(buffer, position, buffer, new CompletionHandler<Integer, ByteBuffer>() {
    @Override
    public void completed(Integer count, ByteBuffer target) {
        // Dùng count và target khi I/O hoàn thành.
    }

    @Override
    public void failed(Throwable error, ByteBuffer target) {
        // Xử lý hoặc chuyển tiếp lỗi; giải phóng tài nguyên khi cần.
    }
});
~~~

*Đoạn trên chỉ là minh họa API của `AsynchronousFileChannel`, giả sử `channel` là file channel đã mở, `buffer` là `ByteBuffer` và đã import `Future`/`CompletionHandler`. Chương trình độc lập đầy đủ nằm ở phần 6.*

| Cách | Điểm mạnh | Điều cần chú ý |
| --- | --- | --- |
| `Future<V>` | Dễ kết hợp vào luồng điều khiển tuần tự, kiểm tra `isDone()` hoặc đợi có timeout | `get()` làm **luồng gọi** chờ; dùng nó ngay sau mỗi operation có thể mất lợi thế không chặn luồng của async I/O |
| `CompletionHandler<V,A>` | Callback được gọi khi operation hoàn thành, không yêu cầu thread gọi đứng đợi | Quản lý trạng thái, buffer, lỗi, đóng channel; giữ callback ngắn và không làm việc blocking lâu |
| `CompletableFuture` tự bọc callback | Hữu ích để nối các bước `thenCompose`/`whenComplete` và tập trung luồng lỗi | NIO.2 không tự trả `CompletableFuture` cho mọi API; cần adapter tự viết hoặc library phù hợp |

**Hai nhầm lẫn quan trọng:**

- “API async” không đồng nghĩa “mỗi bước đều non-blocking”: `Future.get()` vẫn chặn luồng chờ completion, dù operation đã được khởi tạo bất đồng bộ.
- “Async file” không bảo đảm kernel có native asynchronous disk I/O trên mọi hệ điều hành/provider. Cơ chế triển khai có thể sử dụng pool thread để phục vụ I/O; cần đo throughput/latency thực tế trước khi chọn.

Một `CompletionHandler` nhận đối tượng **attachment** do caller truyền vào, hữu ích để mang context cho callback. Ví dụ với file có thể truyền chính `ByteBuffer` như mẫu trên. Completion của channel group thường chạy trên thread pool của group, **không giả định** callback chạy trên thread đã khởi tạo thao tác.

## 3. Nền tảng cần nắm trước khi viết mã

### 3.1. ByteBuffer lưu trạng thái, không chỉ lưu byte[]

Một `ByteBuffer` có các thuộc tính:

- `capacity`: dung lượng cố định.
- `position`: nơi thao tác tiếp theo đọc hoặc ghi.
- `limit`: giới hạn vùng còn có thể thao tác.
- `remaining()` = `limit - position`: số byte còn lại trong trạng thái hiện tại.

Quy trình thường gặp:

~~~text
Nhận dữ liệu từ channel vào buffer:
  clear() hoặc buffer mới -> channel.read(buffer)
  -> đợi hoặc nhận completion -> flip()
  -> decode, parse hoặc lấy dữ liệu

Gửi dữ liệu từ buffer ra channel:
  put(...) -> flip() -> channel.write(buffer)
  -> nếu hasRemaining(), tiếp tục write phần còn lại
~~~

`flip()` đổi buffer từ chế độ ghi sang chế độ đọc: đặt `limit` tại vị trí hiện tại và `position` về 0. `clear()`/`compact()` **không xóa dữ liệu khỏi bộ nhớ**; chỉ thay đổi con trỏ, vì vậy đừng dùng buffer còn chứa dữ liệu nhạy cảm mà không có chính sách phù hợp.

**Không sửa hoặc dùng lại buffer khi operation vẫn pending.** Các phương thức đọc/ghi bất đồng bộ có thể cập nhật `position` và byte content sau khi call trả về. Chỉ tái sử dụng khi nhận completion; không cho hai operation đồng thời sửa cùng buffer nếu không có cơ chế đồng bộ và phân vùng rõ.

### 3.2. Một lần read/write không đồng nghĩa một message

- `read` trả số byte thực đọc; có thể ít hơn `remaining()`.
- `write` trả số byte thực ghi; nếu buffer còn byte, phải gửi tiếp cho đến khi `!buffer.hasRemaining()`.
- Socket `read` trả **-1** khi peer đã đóng đầu gửi và hết dữ liệu; nếu frame đang dở, đó là lỗi protocol.
- TCP là **byte stream**, không giữ ranh giới message do mỗi lần `write` tạo ra. Một message có thể bị chia thành nhiều lần `read`; nhiều message cũng có thể đến trong cùng một buffer.
- Lệnh accept chỉ nhận một **kết nối**, không tự gửi dữ liệu và không xử lý toàn bộ phiên làm việc.

Ví dụ này chọn framing đơn giản: **4 byte big-endian ghi độ dài body**, theo sau là số byte UTF-8 tương ứng. Mặc định `ByteBuffer` dùng `ByteOrder.BIG_ENDIAN`; nếu đổi protocol phải quy định byte order rõ ràng ở cả hai phía. Client/server phải validate length trước khi cấp phát buffer.

## 4. AsynchronousFileChannel: vị trí byte là tham số bắt buộc

Mở file:

~~~java
try (AsynchronousFileChannel file = AsynchronousFileChannel.open(
        path,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE,
        StandardOpenOption.CREATE)) {
    // File channel được close tự động khi ra khỏi try.
}
~~~

*Đoạn minh họa với `Path path` và các import `java.nio.file.StandardOpenOption`, `java.nio.channels.AsynchronousFileChannel`.*

Các đặc điểm:

1. **Không có file cursor dùng chung.** Mỗi `read(buffer, position)` / `write(buffer, position)` yêu cầu **offset long** tính theo byte, bắt đầu từ 0. Đừng nhầm offset với `ByteBuffer.position()`: một cái là vị trí trong *file*, cái còn lại là vị trí trong *buffer*.
2. **Phải cộng offset theo số byte thực truyền**, không cộng theo kích thước buffer định sẵn. Nếu write được 100 byte trong batch 512 byte, lần tiếp theo dùng `filePosition + 100`.
3. `read` có thể trả `-1` khi đọc ở hoặc sau EOF; âm vị trí là không hợp lệ.
4. Nhiều operation có thể outstanding trên file channel, nhưng **không có bảo đảm thứ tự hoàn thành**. Các write chồng lên cùng vùng file và reuse buffer đồng thời rất dễ gây hỏng dữ liệu.
5. `AsynchronousFileChannel.open(path, options, executor, attrs...)` cho phép chỉ định `ExecutorService`; khác với `AsynchronousChannelGroup` được dùng cho socket channels. Nếu không chỉ định, implementation dùng pool mặc định phụ thuộc hệ thống.
6. `file.force(true)` có thể được dùng khi cần yêu cầu đồng bộ dữ liệu/metadata xuống thiết bị theo hợp đồng API, nhưng đó là thao tác có thể block và làm tăng latency; không phải mọi write async đều đồng nghĩa đã durable trên đĩa ngay tại thời điểm ứng dụng nhận completion.

**Khi cập nhật file an toàn:** với yêu cầu thay thế nguyên tệp, một phương án là ghi nội dung vào file tạm, hoàn tất mọi pending write, tùy độ bền mong muốn thực hiện sync/force, đóng channel rồi `Files.move(...)` theo chính sách hệ thống và khả năng hỗ trợ atomic move. Không ghi đè file cấu hình production trực tiếp chỉ vì API có chữ “asynchronous”.

## 5. AsynchronousServerSocketChannel và AsynchronousSocketChannel

**Server socket** bắt đầu ở trạng thái chưa bind; gọi `bind` rồi `accept`:

~~~java
try (AsynchronousServerSocketChannel server = AsynchronousServerSocketChannel
        .open().bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0))) {
    // Port 0: hệ điều hành cấp port trống cho demo loopback.
    Future<AsynchronousSocketChannel> accepted = server.accept();
    // accepted.get() sẽ đợi nếu bạn chọn mô hình Future.
}
~~~

*Đoạn minh họa API, giả sử đã import các lớp liên quan. Không phải server hoàn chỉnh vì chưa có client và chưa đóng accepted channel; ví dụ đầy đủ ở phần 6.*

**Phân biệt hai loại channel:**

- `AsynchronousServerSocketChannel`: chỉ `bind` và `accept`. Server cho nhiều client cần **re-arm** một lần `accept` mới sau mỗi completion; **không** giữ hai accept outstanding trên cùng server vì có thể nhận `AcceptPendingException`.
- `AsynchronousSocketChannel`: kết nối TCP (client hoặc server-accepted peer), `read` và `write`. Một kênh thường cho phép đồng thời **một read pending và một write pending**, nhưng không hai read pending hoặc hai write pending: có thể nhận `ReadPendingException` / `WritePendingException`.
- `connect` bất đồng bộ trên client; bản `Future<Void>` cho phép chờ completion hoặc nhận failure. Đừng gọi read/write như thể connection đã thiết lập trước khi connect thành công.
- Callback `failed(Throwable, attachment)` xử lý lỗi kể cả khi peer bị reset, channel bị đóng hoặc operation pending thất bại; không giả định chỉ có callback `completed`.
- Sau khi xử lý xong, đóng accepted peer và client channel. Đóng server không tự thay thế việc đóng/hoàn tất các phiên client đã được accept.

**Threading:** các socket channel có thể thuộc một `AsynchronousChannelGroup`; group quản lý hạ tầng completion và thread pool. Khi chỉ cần demo nhỏ, dùng default group. Trong hệ thống thật, group dành riêng có thể giúp quản lý lifecycle và chính sách thread, nhưng số thread, CPU quota và thời gian callback cần được benchmark. Đừng đưa công việc nặng (parse file lớn, DB sync, mã hóa CPU-bound) vào completion handler.

## 6. Chương trình Java 17+ hoàn chỉnh: file + TCP echo

Chương trình dưới đây chạy hai bài thực hành liên tiếp:

- **Phần file:** tạo file tạm, ghi chuỗi bằng `AsynchronousFileChannel.write(...)`, chờ Future có timeout, sau đó đọc lại từng phần bằng offset đúng; tự xóa file tạm.
- **Phần TCP:** mở một server trên **loopback** với port tự cấp, accept đúng một client trong callback; cả hai phía truyền frame độ dài 4 byte + payload. Helper `readFully`/`writeFully` dùng callback để tiếp tục các transfer còn thiếu.
- Main/test client dùng `get(5, TimeUnit.SECONDS)` để demo có thứ tự và không đợi vô hạn. **Đây là đợi có chặn trên luồng main**; phần callback xử lý peer hoạt động theo cơ chế completion bất đồng bộ. Trong server ứng dụng thật, không gọi `get()` trên thread xử lý completion.

**Lưu vào tệp `AsyncNioDemo.java`:**

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public final class AsyncNioDemo {
    private static final int MAX_FRAME = 64 * 1024;
    private static final String MESSAGE = "Hello async NIO.2";

    public static void main(String[] args) throws Exception {
        demoFile();
        demoTcp();
    }

    private static void demoFile() throws Exception {
        Path path = Files.createTempFile("async-nio2-", ".txt");
        try {
            try (AsynchronousFileChannel file = AsynchronousFileChannel.open(
                    path, StandardOpenOption.READ, StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {
                byte[] data = MESSAGE.getBytes(StandardCharsets.UTF_8);
                ByteBuffer src = ByteBuffer.wrap(data);
                long position = 0L;
                while (src.hasRemaining()) {
                    int n = file.write(src, position).get(5, TimeUnit.SECONDS);
                    if (n <= 0) throw new IOException("File write made no progress");
                    position += n;
                }

                ByteBuffer dst = ByteBuffer.allocate(data.length);
                position = 0L;
                while (dst.hasRemaining()) {
                    int n = file.read(dst, position).get(5, TimeUnit.SECONDS);
                    if (n < 0) throw new EOFException("Unexpected file EOF");
                    if (n == 0) continue;
                    position += n;
                }
                dst.flip();
                System.out.println("File: " + StandardCharsets.UTF_8.decode(dst));
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }

    private static CompletableFuture<Void> readFully(
            AsynchronousSocketChannel channel, ByteBuffer dst) {
        CompletableFuture<Void> done = new CompletableFuture<>();
        if (!dst.hasRemaining()) {
            done.complete(null);
            return done;
        }
        CompletionHandler<Integer, Void> callback = new CompletionHandler<>() {
            @Override
            public void completed(Integer n, Void unused) {
                if (n < 0) {
                    done.completeExceptionally(new EOFException("Socket closed mid-frame"));
                } else if (dst.hasRemaining()) {
                    channel.read(dst, null, this);
                } else {
                    done.complete(null);
                }
            }

            @Override
            public void failed(Throwable error, Void unused) {
                done.completeExceptionally(error);
            }
        };
        channel.read(dst, null, callback);
        return done;
    }

    private static CompletableFuture<Void> writeFully(
            AsynchronousSocketChannel channel, ByteBuffer src) {
        CompletableFuture<Void> done = new CompletableFuture<>();
        if (!src.hasRemaining()) {
            done.complete(null);
            return done;
        }
        CompletionHandler<Integer, Void> callback = new CompletionHandler<>() {
            @Override
            public void completed(Integer n, Void unused) {
                if (n < 0) {
                    done.completeExceptionally(new EOFException("Socket closed on write"));
                } else if (src.hasRemaining()) {
                    channel.write(src, null, this);
                } else {
                    done.complete(null);
                }
            }

            @Override
            public void failed(Throwable error, Void unused) {
                done.completeExceptionally(error);
            }
        };
        channel.write(src, null, callback);
        return done;
    }

    private static CompletableFuture<Void> echoOneFrame(AsynchronousSocketChannel peer) {
        ByteBuffer header = ByteBuffer.allocate(Integer.BYTES);
        return readFully(peer, header).thenCompose(unused -> {
            header.flip();
            int length = header.getInt();
            if (length < 0 || length > MAX_FRAME) {
                return CompletableFuture.failedFuture(new IOException("Invalid frame length"));
            }
            ByteBuffer payload = ByteBuffer.allocate(length);
            return readFully(peer, payload).thenCompose(ignored -> {
                payload.flip();
                ByteBuffer response = ByteBuffer.allocate(Integer.BYTES + length);
                response.putInt(length).put(payload).flip();
                return writeFully(peer, response);
            });
        });
    }

    private static void demoTcp() throws Exception {
        try (AsynchronousServerSocketChannel server = AsynchronousServerSocketChannel
                .open().bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
            CompletableFuture<Void> served = new CompletableFuture<>();
            server.accept(null, new CompletionHandler<AsynchronousSocketChannel, Void>() {
                @Override
                public void completed(AsynchronousSocketChannel peer, Void unused) {
                    echoOneFrame(peer).whenComplete((ignored, error) -> {
                        try {
                            peer.close();
                        } catch (IOException closeError) {
                            if (error == null) {
                                served.completeExceptionally(closeError);
                                return;
                            }
                        }
                        if (error == null) served.complete(null);
                        else served.completeExceptionally(error);
                    });
                }

                @Override
                public void failed(Throwable error, Void unused) {
                    served.completeExceptionally(error);
                }
            });

            client.connect(server.getLocalAddress()).get(5, TimeUnit.SECONDS);
            byte[] data = MESSAGE.getBytes(StandardCharsets.UTF_8);
            ByteBuffer request = ByteBuffer.allocate(Integer.BYTES + data.length);
            request.putInt(data.length).put(data).flip();
            writeFully(client, request).get(5, TimeUnit.SECONDS);

            ByteBuffer replyHeader = ByteBuffer.allocate(Integer.BYTES);
            readFully(client, replyHeader).get(5, TimeUnit.SECONDS);
            replyHeader.flip();
            int replyLength = replyHeader.getInt();
            if (replyLength < 0 || replyLength > MAX_FRAME) {
                throw new IOException("Invalid reply frame length");
            }

            ByteBuffer reply = ByteBuffer.allocate(replyLength);
            readFully(client, reply).get(5, TimeUnit.SECONDS);
            reply.flip();
            System.out.println("TCP echo: " + StandardCharsets.UTF_8.decode(reply));
            served.get(5, TimeUnit.SECONDS);
        }
    }
}
~~~

### Biên dịch và chạy

Cần JDK 17+ và môi trường cho phép mở kết nối TCP loopback:

~~~bash
javac -encoding UTF-8 --release 17 AsyncNioDemo.java
java AsyncNioDemo
~~~

**Stdout khi chạy thành công:**

~~~text
File: Hello async NIO.2
TCP echo: Hello async NIO.2
~~~

Chương trình tạo file tạm bằng `Files.createTempFile` và xóa ở `finally`, nên bạn không cần tự tạo đường dẫn hoặc port. **Demo không lắng nghe Internet**: server chỉ bind vào địa chỉ loopback, chọn một cổng còn trống, phục vụ **đúng một** connection rồi kết thúc.

Nếu chạy trong sandbox hoặc CI cấm socket/network, phần TCP có thể thất bại do quyền môi trường; đó không chứng minh NIO.2 đã bị loại bỏ. Trong một ứng dụng thật, bảo vệ `server.getLocalAddress()`, chính sách bind và quyền socket theo thiết kế triển khai.

### Đọc chương trình theo luồng sự kiện

~~~text
main
  |
  +--> demoFile: write Future -> get -> tăng file offset
  |                 -> read Future -> get -> flip -> decode
  |
  +--> demoTcp: server.bind(loopback, ephemeral port)
                 |
                 +--> server.accept(..., handler)  [khởi tạo, không đợi]
                 |
                 +--> client.connect(...).get     [main đợi kết nối]
                 +--> writeFully(request).get     [main đợi response]
                 |
                 +--> server callback nhận peer
                        -> readFully(header 4 byte)
                        -> validate length <= MAX_FRAME
                        -> readFully(payload)
                        -> writeFully(header + payload)
                        -> close peer + complete served
                 |
                 +--> client đọc header/payload -> decode
                 +--> served.get -> close client/server
~~~

**Tại sao helper dùng `hasRemaining()`?** Socket có thể hoàn thành một lần read/write với ít byte hơn yêu cầu, nên helper tái khởi tạo operation đến khi buffer đầy/được gửi hết. Khi peer đóng giữa frame, `readFully` báo lỗi thay vì giải mã nội dung thiếu. Một lần write hoàn thành **không đồng nghĩa** dữ liệu đã được application bên kia xử lý; chỉ phản ánh số byte được chấp nhận bởi hệ thống gửi.

**Tại sao giới hạn 64 KiB?** Tránh client gửi một giá trị length cực lớn khiến server tạo một `ByteBuffer.allocate(length)` vượt bộ nhớ. Giới hạn này chỉ phù hợp demo; production cần ngân sách theo protocol, tổng số connection, queue và memory capacity.

## 7. Mở rộng từ một kết nối thành server thật

Mã trên chấp nhận một client vì mục tiêu học tập. Với server nhiều client, xây dựng vòng `accept` kiểu bất đồng bộ:

1. Bind một lần; giữ cờ `running`.
2. Gọi `accept` **một lần**.
3. Khi `completed(peer)`, kiểm tra `running` và **đăng ký lượt `accept` tiếp theo** trước hoặc theo chính sách giới hạn tải; sau đó xử lý `peer` độc lập.
4. Mỗi peer có state riêng cho protocol: header, payload, buffer, timeout, socket, số byte đã đọc/ghi, trạng thái đóng.
5. Khi server shutdown, ngừng accept, đóng listener socket, hoàn tất hoặc hủy từng session theo grace period, đóng tất cả accepted channels và các tài nguyên của group/executor do ứng dụng sở hữu.

**Không được** gọi hai `accept` đồng thời trên một server channel. Một chiến lược re-arm phải bảo đảm khi callback được gọi là lượt accept trước đã hoàn thành, rồi mới yêu cầu lượt mới. Nếu giới hạn số peer đồng thời, có thể tạm dừng nhận lượt tiếp theo theo chiến lược backpressure và tiếp tục khi capacity được trả lại.

### 7.1. Đừng đọc hai lần cùng lúc trên một socket

Mô hình một pending read/ một pending write trên mỗi `AsynchronousSocketChannel` có nghĩa:

- Đọc header hoàn tất rồi mới đọc body, không cùng lúc khởi tạo hai read lên cùng channel.
- Khi có nhiều response, cần **write queue** cho từng peer để gửi lần lượt và giữ thứ tự frame; hai luồng gọi `write` song song có thể gây `WritePendingException`, trộn nội dung hoặc sai framing.
- Một read và một write có thể pending đồng thời để thực hiện giao tiếp song công, nhưng mỗi bên cần buffer và lifecycle rõ ràng.
- Trong mô hình publish nhiều message, queue bị tăng không giới hạn là **memory leak theo tải** dù không có object leak thông thường. Đặt giới hạn byte/connection hoặc tổng số connection, tạm ngừng đọc, chặn producer hoặc đóng session theo policy khi vượt ngưỡng.

### 7.2. Xử lý timeout, cancel và shutdown

- `Future.get(timeout, unit)` chỉ giới hạn thời gian **đợi của caller**. Khi ném `TimeoutException`, operation không tự động bảo đảm đã dừng. Cần cancellation/close hoặc timeout I/O theo API phù hợp và chính sách cleanup.
- `Future.cancel(...)` không bảo đảm có thể hủy thao tác I/O dưới tầng hệ điều hành. Javadoc cho phép trạng thái channel sau cancellation mang tính implementation-specific; đừng assume có thể tái sử dụng y như trước.
- `AsynchronousSocketChannel.read/write` cũng có overload nhận timeout trực tiếp cùng handler; chọn deadline theo từng connection/phase. Kết thúc do timeout cần log/cleanup phù hợp, không treo peer vĩnh viễn.
- Khi `close()` được gọi trong lúc có operation pending, các operation có thể thất bại với `AsynchronousCloseException` hoặc lỗi liên quan. Trong quá trình shutdown bình thường, phân biệt log lỗi đóng có chủ đích với lỗi mạng thực sự.
- Nếu tự tạo `AsynchronousChannelGroup`, `shutdown()` là quá trình ngừng có trật tự, không đóng ngay mọi channel đang mở; group chỉ terminate khi các channel đã đóng và callback xong. `shutdownNow()` sẽ đóng các channel trong group. Gọi `awaitTermination` ở luồng quản lý shutdown, **không block completion handler**.
- Không giữ thread của executor bằng một vòng lặp `while(true)`/`sleep` để “chờ” I/O; callback và readiness của provider mới là điểm chuyển trạng thái.

### 7.3. Không chặn completion handler

Các callback trong group thường chạy trên pool của group; một số completion có thể gọi handler trực tiếp trong thread của group nếu I/O xong ngay. Hệ quả: **đừng chạy tác vụ blocking, CPU-heavy hoặc dùng `get()` bên trong callback**. Nếu cần parsing nặng, nén, truy vấn database hoặc cryptography, chuyển sang executor dành cho business work, sau đó quay lại state machine khi công việc hoàn tất.

`CompletableFuture.thenCompose`/`whenComplete` mặc định có thể thực thi inline trong thread hoàn thành future, chứ không luôn tách sang worker khác. Khi công việc sau completion nặng, dùng `thenApplyAsync`/`thenComposeAsync` với executor được quản lý và có bounded work queue khi cần. Tránh dùng vô thức common pool nếu cần kiểm soát capacity và graceful shutdown.

## 8. Xử lý lỗi đúng: EOF, partial, protocol và resource cleanup

| Tình huống | Điều quan sát | Cách xử lý |
| --- | --- | --- |
| File read tới cuối | `read` trả `-1` | Nếu đang chờ số byte bắt buộc, ném `EOFException`; nếu đọc đến hết file bình thường, kết thúc vòng lặp. |
| File/socket write một phần | Số byte ghi nhỏ hơn `remaining` ban đầu | Giữ buffer và cộng offset file theo số byte thực ghi, hoặc reissue socket write đến khi `!hasRemaining()`. |
| Socket peer đóng giữa frame | `readFully` thấy `-1` khi buffer chưa đầy | Coi frame không hợp lệ, close peer; không decode body thiếu. |
| Frame length âm/quá lớn | Header 4 byte không nằm trong giới hạn | Từ chối request trước khi cấp phát payload để tránh memory exhaustion. |
| Peer disconnect giữa write | Callback `failed` hoặc lỗi đóng channel | Hoàn tất session thất bại, giải phóng buffer/socket, không retry vô hạn trên connection đã hỏng. |
| Write/read trùng trên cùng socket | `ReadPendingException` / `WritePendingException` | Dùng state machine hoặc queue, chỉ một operation mỗi chiều đang pending. |
| Đóng channel khi pending | Operation có thể hoàn tất bằng exception | Điều phối shutdown, kiểm tra `isOpen()` khi thích hợp nhưng vẫn phải xử lý race. |
| Timeout hoặc task bị cancel | Chờ hết hạn nhưng operation có thể còn chạy | Áp dụng chính sách close/cancel và đảm bảo callback/future không treo resource. |
| Lỗi handler | Handler thất bại trong callback | Complete error/future, log có ngữ cảnh, close đúng ownership; không để exception phá vỡ toàn bộ accept loop. |

**Quan trọng về ownership:** trong chương trình mẫu, try-with-resources sở hữu server/client và closure ở callback sở hữu accepted peer; `Files.deleteIfExists` nằm ở `finally`. Trong production, tách một đối tượng session để mọi đường đi thành công, lỗi, timeout hoặc shutdown đi qua cùng một hàm cleanup idempotent.

**Quan trọng về an toàn path:** không sử dụng trực tiếp tên file do client gửi vào `Path.of(...)` mà chưa kiểm soát thư mục gốc, traversal, symlinks và quyền truy cập. Demo chỉ dùng file tạm do hệ thống tạo, không nhận đường dẫn từ network. Với server Internet, còn cần giới hạn concurrent clients, TLS hoặc endpoint bảo vệ, xác thực/ủy quyền theo nghiệp vụ, timeout và giới hạn payload.

## 9. Hiệu năng và khi nào nên chọn hướng khác

### 9.1. Async không tự bảo đảm nhanh hơn blocking

Khởi tạo I/O không chặn giúp một luồng có thể điều phối nhiều thao tác, nhất là khi phục vụ nhiều socket. Nhưng có chi phí từ callback, chuyển context, buffer lifecycle, quản lý queue và pool; với file nhỏ hoặc một connection, code đồng bộ có thể đơn giản và hiệu quả hơn.

Lựa chọn thực tế:

| Lựa chọn | Hợp lý khi | Đánh đổi |
| --- | --- | --- |
| `Files.readAllBytes`, `Files.writeString` | Tệp nhỏ, xử lý tuần tự, không cần overlap I/O | Chặn thread; `readAllBytes` cần RAM chứa cả tệp; giới hạn kích thước tệp. |
| `FileChannel` đồng bộ | Đọc/ghi file offset hoặc memory mapping có kiểm soát | Luồng gọi có thể chờ I/O; code rõ ràng và dễ kiểm thử. |
| `AsynchronousFileChannel` | Pipeline file nhiều operation với callback hoặc xử lý chồng lấp, có lý do đo được | Không có implicit cursor; cần quản lý offset, buffer, completion, executor. |
| `SocketChannel` + `Selector` | Event loop có kiểm soát trên NIO nonblocking | Tự quản lý readiness/interest ops; không phải cùng mô hình với completion handler. |
| `AsynchronousSocketChannel` | Server/client hoạt động theo callback và nhiều phiên bất đồng bộ | State machine, partial I/O, backpressure và lifecycle phức tạp. |
| Blocking socket trên **virtual thread (Java 21+)** | Nhiều session mà muốn code tuần tự dễ đọc, môi trường đã hỗ trợ virtual threads | Vẫn cần framing, timeout, resource cap; phải đánh giá pinning, library và nhu cầu I/O thực tế. |

**Virtual threads** là lựa chọn hiện đại hợp lệ cho nhiều server I/O-bound. Chúng không biến CPU-bound computation thành nhanh hơn và không thay thế quản trị bộ nhớ/connection. Không có yêu cầu mặc định “dùng asynchronous channel vì nó mới hơn”; hãy ưu tiên mô hình có độ phức tạp hợp lý và đo kết quả thực.

### 9.2. Bộ chỉ số nên benchmark

- Throughput (message/s hoặc byte/s), p95/p99 end-to-end latency và số connection đồng thời.
- CPU của business work + worker/completion threads, thread count, context switches.
- Heap/RSS, số buffer retained/queued, allocation rate và GC pauses.
- Tốc độ đọc ghi storage và p95/p99 disk latency; file system cache nóng/lạnh.
- Backpressure: pending writes, queue length, peer chậm, lỗi timeout/EOF, tỷ lệ disconnect.
- Khi so sánh, cố định workload, kích thước message, concurrency, phần cứng, hệ điều hành, JDK, memory limit và warm-up của ứng dụng.

Một test đơn lẻ trên loopback với payload nhỏ **không phải benchmark năng lực Internet server**. Nó kiểm chứng correctness và đường đi API. Một kiến trúc production cần load test có message size distribution, client chậm, dữ liệu lỗi, packet segmentation và giới hạn tải.

## 10. Bài tập mở rộng theo mức độ

1. **Đọc file theo nhiều block:** mở file chỉ đọc, lấy `size()`, chia công việc thành các khoảng byte không chồng lấp, viết callback cho mỗi block và ghép kết quả **theo offset** chứ không theo thứ tự completion. Giới hạn số block đang outstanding.
2. **Chuyển file lớn:** không gọi `Files.readAllBytes` cho tệp lớn; đọc từng chunk vào một buffer được quản lý, write sang socket có backpressure, chỉ đọc chunk tiếp khi write chunk trước đã hoàn tất.
3. **Nhiều client:** tái đăng ký `accept`, tạo session độc lập, giới hạn connection count và bounded write queue; thực hiện đóng tất cả session khi shutdown.
4. **Server từ chối malformed frame:** gửi header length âm hoặc rất lớn; xác nhận server không cấp phát buffer theo giá trị đó, đóng peer và không làm ảnh hưởng connection khác.
5. **Partial transfer:** gửi header từng byte và payload thành nhiều đợt bằng client test; xác nhận server vẫn ghép đúng một frame. Không sửa server dựa trên giả định read luôn nhận đủ buffer.
6. **Timeout/disconnect:** kết nối nhưng không gửi body, hoặc đóng socket sau khi gửi 2/4 byte header; xác nhận session trả lỗi, không giữ queue/peer vĩnh viễn.
7. **So sánh kiến trúc:** với cùng protocol, thử blocking socket + virtual threads trên JDK 21+, rồi đo p99 latency/throughput/RSS cùng concurrency. Đừng chỉ so số dòng code.

## 11. Những lỗi phổ biến cần tránh

1. **Tin rằng `Future.get()` không chặn:** operation có thể async nhưng `get` vẫn block thread gọi.
2. **Không tăng file offset sau partial write:** vòng lặp ghi đè hoặc ghi lặp dữ liệu.
3. **Decode buffer trước `flip()`:** kết quả rỗng, lẫn byte chưa ghi hoặc sai giới hạn.
4. **Đóng/reuse buffer khi operation pending:** dữ liệu không xác định do I/O sửa buffer sau khi caller trả về.
5. **Cho rằng một lần socket read là một message:** TCP không bảo đảm message boundary; cần framing.
6. **Không xử lý `-1` / partial EOF:** treo chờ hoặc coi payload cụt là bản tin hợp lệ.
7. **Không kiểm tra độ dài frame:** client độc hại có thể gây cấp phát khổng lồ.
8. **Đăng ký hai accept/read/write cùng chiều trên một channel:** phát sinh pending exception, luồng trạng thái khó kiểm soát.
9. **Làm việc nặng bên trong completion handler:** bão hòa pool xử lý I/O và tăng latency.
10. **Không kiểm soát queue và số client:** tốc độ producer vượt tốc độ write, bộ nhớ tăng không giới hạn.
11. **Đợi bằng timeout nhưng không cleanup operation:** caller dừng chờ nhưng channel/buffer vẫn còn pending.
12. **Quên đóng accepted peer, server hoặc executor/group:** rò tài nguyên và giữ thread còn chạy.
13. **Coi API async file là native kernel AIO mọi nơi:** khác biệt implementation/provider cần đo thực tế.
14. **Lạm dụng async cho tác vụ đơn giản:** đôi khi blocking API hoặc virtual threads rõ ràng, dễ bảo trì hơn.

## 12. Checklist khi triển khai

- [ ] Đã chọn đúng channel: file, socket client hay server socket.
- [ ] Với file: mỗi operation có offset byte đúng; cập nhật bằng **số byte thực**.
- [ ] Với socket: có framing, validate length, read/write đến khi buffer hoàn thành.
- [ ] Chỉ có tối đa một pending read và một pending write trên một socket; accept được re-arm đúng.
- [ ] Buffer không bị dùng lại khi I/O còn outstanding; decode UTF-8 sau khi `flip()`.
- [ ] Thành công, failed, timeout, cancel, EOF và shutdown đều dẫn đến cleanup rõ ràng.
- [ ] Callback ngắn, không chờ `get`/DB/I/O nặng; có giới hạn connection và queue.
- [ ] Chạy thử trên loopback, payload phân mảnh, peer đóng giữa frame và dữ liệu malformed.
- [ ] Với server thực: có bảo vệ mạng, giới hạn tài nguyên, observability và graceful shutdown.
- [ ] Đã cân nhắc blocking I/O/virtual threads khi chúng đáp ứng cùng SLO với độ phức tạp thấp hơn.

## 13. API tham khảo chính thức, vẫn áp dụng

- [Oracle JDK 25 — `AsynchronousChannel`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/AsynchronousChannel.html): `Future`, `CompletionHandler`, hủy/đóng channel.
- [Oracle JDK 25 — `AsynchronousFileChannel`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): vị trí file tường minh, read/write, force, thread pool.
- [Oracle JDK 25 — `AsynchronousServerSocketChannel`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): bind, accept, một accept pending.
- [Oracle JDK 25 — `AsynchronousSocketChannel`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): connect, read/write, pending operation, timeout.
- [Oracle JDK 25 — `AsynchronousChannelGroup`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html): thread pool, completion handler, shutdown/awaitTermination.
- [Oracle JDK 25 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/ByteBuffer.html): position/limit/flip/compact.
- [Oracle — Virtual Threads (JDK 21+)](https://docs.oracle.com/en/java/javase/25/core/virtual-threads.html): lựa chọn thực thi đồng bộ theo phong cách tuần tự cho ứng dụng nhiều kết nối.

**Kết luận:** Kênh bất đồng bộ cho phép **khởi tạo I/O rồi nhận kết quả sau**; phần khó nhất không phải gọi `read` hay `write`, mà là quản lý **byte thực truyền, buffer, state machine, lỗi và vòng đời tài nguyên**. Với tệp và socket, luôn xác định rõ đâu là future blocking wait, đâu là completion handler, và chọn kiến trúc theo đặc điểm workload thay vì tên API.