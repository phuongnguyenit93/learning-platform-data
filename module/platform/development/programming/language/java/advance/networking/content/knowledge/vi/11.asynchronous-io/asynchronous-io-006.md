# Một thao tác đọc và một thao tác ghi đang chờ: giới hạn thực thi đồng thời trong Java AsynchronousSocketChannel

Trong Java NIO.2, **`AsynchronousSocketChannel` hỗ trợ một thao tác đọc và một thao tác ghi diễn ra đồng thời trên cùng một TCP channel**, nhưng **tại mỗi thời điểm chỉ được có tối đa một thao tác đọc đang chờ và tối đa một thao tác ghi đang chờ**. Nếu ứng dụng bắt đầu một lần `read` mới khi lần `read` trước chưa hoàn thành, Java ném **`ReadPendingException`**. Tương tự, bắt đầu `write` mới khi lần `write` cũ chưa hoàn thành gây **`WritePendingException`**.

Đây là giới hạn của **I/O operation đang outstanding**, không phải giới hạn “một thread” hoặc “một request cho cả máy chủ”. Cùng một channel có thể vừa chờ đọc vừa chờ ghi; nhiều channel khác nhau có bộ giới hạn độc lập. Bài này thuộc chủ đề **I/O bất đồng bộ** và giải thích chính xác semantics, cách quản lý `Future`/`CompletionHandler`, ByteBuffer và hàng đợi để không phát sinh lỗi khi nhiều tác vụ cùng gửi/nhận.

Hai ví dụ cuối là chương trình **Java 17+ hoàn chỉnh**, chạy trên `127.0.0.1` với cổng động, không cần Internet hay server bên ngoài.

## 1. “Đang chờ” (outstanding/pending) thực sự là gì?

Một lần gọi:

~~~java
Future<Integer> readResult = channel.read(readBuffer);
~~~

là **khởi tạo** một thao tác đọc bất đồng bộ. Trả về `Future` **không** có nghĩa bytes đã được đọc xong. I/O provider có thể đang chờ dữ liệu hoặc xử lý completion. Kể từ lúc thao tác được chấp nhận đến khi **hoàn thành/thất bại**, nó chiếm **slot đọc** của channel.

Tương tự:

~~~java
Future<Integer> writeResult = channel.write(writeBuffer);
~~~

chiếm **slot ghi** trong khi write outstanding. Khi thao tác hoàn thành, ứng dụng có thể tiếp tục khởi tạo thao tác cùng loại (nếu channel vẫn ở trạng thái hợp lệ).

Khung tư duy:

~~~text
Một AsynchronousSocketChannel đã connect
┌───────────────────────────────────────────────────────────┐
│ Read slot:   [FREE] -- read() --> [PENDING] --> [FREE]     │
│                           |                               │
│                           +-- read() lần 2 --> EXCEPTION   │
│                                                           │
│ Write slot:  [FREE] -- write() -> [PENDING] --> [FREE]     │
│                           |                               │
│                           +-- write() lần 2 -> EXCEPTION   │
└───────────────────────────────────────────────────────────┘

Read pending + Write pending trên CÙNG channel: ĐƯỢC PHÉP.
Hai read pending trên CÙNG channel: KHÔNG ĐƯỢC PHÉP.
Hai write pending trên CÙNG channel: KHÔNG ĐƯỢC PHÉP.
~~~

Các nhãn `FREE/PENDING` là mô hình minh họa, không phải enum trong Java API. Gọi `read` một lần rồi `read` tiếp **ngay sau đó** không tự tạo một “queue đọc” trong channel. Nếu lần đọc trước vẫn pending, API ném exception tại lần gọi tiếp theo.

**Đừng suy luận “mỗi connection chỉ được một I/O operation tổng cộng”.** Giới hạn là **một read cộng một write**; hai hướng của TCP full-duplex có thể tiến triển độc lập.

## 2. Ma trận thao tác đồng thời: cái gì hợp lệ?

| Trạng thái hiện tại của cùng một channel | Thao tác mới | Kết quả theo hợp đồng API |
| --- | --- | --- |
| Chưa có read pending | `read(buffer)` | Có thể khởi tạo read |
| Đã có read pending | Thêm `read(otherBuffer)` | `ReadPendingException` |
| Đã có read pending | `write(buffer)` khi không có write pending | **Được phép**, read và write có thể overlap |
| Chưa có write pending | `write(buffer)` | Có thể khởi tạo write |
| Đã có write pending | Thêm `write(otherBuffer)` | `WritePendingException` |
| Đã có write pending | `read(buffer)` khi không có read pending | **Được phép** |
| Read ở channel A và read ở channel B | Cả hai cùng pending | **Được phép**: hai channel có trạng thái riêng |
| Có một read + một write pending trên channel A | Thêm read ở channel B | Được phép, nếu channel B hợp lệ |

Quan trọng: `ReadPendingException` hoặc `WritePendingException` chỉ xuất hiện **khi thao tác trước thực sự chưa hoàn thành**. Một `write` nhỏ vào socket có kernel buffer trống có thể hoàn thành cực nhanh; gọi hai lần liên tục **không đảm bảo** lần thứ hai ném `WritePendingException`. Không nên viết unit test dựa trên việc socket phải chậm. Để test logic điều phối, dùng state/queue điều khiển được hoặc một tình huống pending chắc chắn (như read chưa có dữ liệu).

Giới hạn này có ở **`AsynchronousSocketChannel`**, không được suy rộng rằng mọi lớp async I/O của Java đều có đúng một read và một write. Ví dụ `AsynchronousFileChannel` có các thao tác theo file position và quy tắc concurrency riêng. Kiểm tra contract của **từng loại channel**.

## 3. API liên quan: Future và CompletionHandler

Java có hai cách bắt đầu thao tác async trên `AsynchronousSocketChannel`:

### 3.1. Future: lấy kết quả về sau

~~~java
Future<Integer> readFuture = channel.read(dst);
Future<Integer> writeFuture = channel.write(src);

// Có thể làm công việc khác ở đây, hoặc chờ nếu chương trình yêu cầu.
int bytesRead = readFuture.get();
int bytesWritten = writeFuture.get();
~~~

Đây là **snippet** trong một phương thức đã có channel kết nối, buffer và imports. `Future.get()` **chặn thread đang gọi get** cho đến khi hoàn tất; bản thân `channel.read(dst)` là lời gọi khởi tạo I/O async.

- Với `read`, kết quả `n > 0` là số bytes nhận; `0` có thể xảy ra với buffer không còn chỗ hoặc theo điều kiện thao tác; `-1` báo **end-of-stream/EOF**.
- Với `write`, kết quả là số bytes đã chuyển từ buffer sang socket, có thể **nhỏ hơn số bytes cần gửi**. Completion không chứng minh peer đã đọc dữ liệu.
- `get()` có thể ném `ExecutionException` (nguyên nhân thật nằm ở `getCause()`) hoặc `InterruptedException`; `get(timeout, unit)` còn có thể ném `TimeoutException` khi **việc chờ kết quả của caller** quá thời gian.
- Một `Future` có thể hoàn tất rất nhanh trước khi code kịp gọi `get()`. Điều này không thay đổi rule: tối đa một thao tác **đang outstanding** theo từng hướng I/O.

Lưu ý: nếu dùng `Future.get(1, SECONDS)` và nhận `TimeoutException`, **không được kết luận I/O đã dừng**. Đây là timeout của việc *đợi Future*, không phải chắc chắn timeout của operation. Thao tác có thể còn pending; khởi tạo read/write cùng loại ngay sau timeout có thể gây pending exception.

### 3.2. CompletionHandler: thông báo thành công hoặc lỗi

Khi dùng callback:

~~~java
channel.read(dst, dst, new CompletionHandler<Integer, ByteBuffer>() {
    @Override
    public void completed(Integer count, ByteBuffer buffer) {
        // Thao tác đọc đã hoàn thành: kiểm tra count, xử lý bytes.
    }

    @Override
    public void failed(Throwable error, ByteBuffer buffer) {
        // Thao tác đọc thất bại: ghi log, đóng channel/cleanup.
    }
});
~~~

Đây là **snippet**, cần `import java.nio.channels.CompletionHandler;`, `ByteBuffer` và biến `channel` hợp lệ. Tham số attachment (ở đây là `dst`) được trả lại cho handler để nối thao tác với state của yêu cầu/kết nối.

Có thêm các overload với timeout, ví dụ:

~~~java
channel.read(
    dst, 2, TimeUnit.SECONDS, attachment, handler);
channel.write(
    src, 2, TimeUnit.SECONDS, attachment, handler);
~~~

Đây là snippet; `attachment`, `handler` và `TimeUnit` được khai báo ở nơi gọi. Những overload này quy định **I/O timeout**: nếu không hoàn tất trong thời hạn, handler có thể được gọi theo nhánh `failed` với `InterruptedByTimeoutException`. Khác biệt quan trọng với `Future.get(timeout)` sẽ được giải thích ở phần timeout.

**Pending exception xảy ra khi bắt đầu operation mới**, không phải “lỗi đọc được chuyển vào callback” theo nghĩa luôn gọi `failed`. Ví dụ gọi `read(...)` khi còn read outstanding có thể ném `ReadPendingException` **ngay ở thread gọi method**; application phải tự quản lý serializing operations trước khi gửi chúng cho provider.

## 4. API contract: thread-safe channel ≠ unlimited concurrent operations

Javadoc nêu rõ `AsynchronousSocketChannel` **safe for use by multiple concurrent threads**, đồng thời có tối đa một read và một write outstanding. Hai nhận định không mâu thuẫn.

- **Thread-safe channel:** Nhiều thread có thể tham chiếu cùng channel và gọi các phương thức thích hợp mà không phá vỡ internal state của channel.
- **Operation concurrency limit:** Hai thread gọi `read` đồng thời trên **cùng channel** có thể đụng giới hạn pending; một thao tác có thể bị từ chối bằng `ReadPendingException`.
- **Buffer ownership:** `ByteBuffer` **không thread-safe** theo nghĩa cho phép nhiều thread tự ý sửa `position/limit/content` cùng lúc. Trong thời gian I/O outstanding, không chỉnh buffer đó ở thread khác; chờ completion trước khi đọc/sửa/reuse.
- **Completion callbacks:** Không giả định callbacks luôn chạy trong cùng thread khởi tạo hoặc theo thứ tự mọi operation. Khi callback và business logic cùng sửa connection state, dùng một cơ chế điều phối/đồng bộ rõ ràng.

**Quy tắc thực hành:** Để một connection manager (actor, event loop hoặc synchronized per-connection state) sở hữu “read slot”, “write slot”, input/output buffers và output queue. Điều đó tránh hai handler khác nhau vô tình cùng gọi `write` lên một channel.

## 5. Ví dụ hoàn chỉnh: phát hiện read pending và vừa đọc vừa ghi

Chương trình sau dùng **ba asynchronous channels**: một `AsynchronousServerSocketChannel` để lắng nghe và hai `AsynchronousSocketChannel` đại diện hai đầu kết nối TCP trên máy. Cấu trúc này cho phép test có kiểm soát:

1. Server bind `127.0.0.1:0`, hệ điều hành cấp port động.
2. Server gọi `accept()`, client gọi `connect()` rồi chờ kết nối thành công.
3. Client bắt đầu `read(response)` **trước khi server gửi gì**: một read pending.
4. Client gọi read lần thứ hai, bắt `ReadPendingException`; đây là kiểm thử ổn định vì server vẫn chưa gửi phản hồi.
5. **Trong lúc read của client đang pending**, chính client gọi `write("ping")`: đây là trường hợp được phép.
6. Server nhận đủ 4 byte rồi gửi `"pong"`; client đọc đủ phản hồi. Mọi I/O có chờ `get(3, SECONDS)` để demo không đợi vô hạn.

Tạo file **`OneReadOneWriteDemo.java`** (UTF-8):

~~~java
import java.io.EOFException;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.ReadPendingException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class OneReadOneWriteDemo {
    private static void writeAll(
            AsynchronousSocketChannel ch, ByteBuffer src) throws Exception {
        while (src.hasRemaining()) {
            int n = ch.write(src).get(3, TimeUnit.SECONDS);
            if (n < 0) {
                throw new EOFException("Write channel closed");
            }
        }
    }

    private static ByteBuffer readExactly(
            AsynchronousSocketChannel ch, int bytes) throws Exception {
        ByteBuffer dst = ByteBuffer.allocate(bytes);
        while (dst.hasRemaining()) {
            int n = ch.read(dst).get(3, TimeUnit.SECONDS);
            if (n < 0) {
                throw new EOFException("Premature EOF");
            }
        }
        dst.flip();
        return dst;
    }

    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open();
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {

            listener.bind(new InetSocketAddress("127.0.0.1", 0));
            InetSocketAddress address =
                    (InetSocketAddress) listener.getLocalAddress();

            Future<AsynchronousSocketChannel> accepting = listener.accept();
            client.connect(address).get(3, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel server =
                         accepting.get(3, TimeUnit.SECONDS)) {

                ByteBuffer response = ByteBuffer.allocate(4);

                // Chưa ai gửi dữ liệu về phía client: read vẫn pending.
                Future<Integer> pendingRead = client.read(response);
                boolean rejectedSecondRead = false;

                try {
                    client.read(ByteBuffer.allocate(4));
                } catch (ReadPendingException expected) {
                    rejectedSecondRead = true;
                }

                if (!rejectedSecondRead) {
                    throw new AssertionError("Expected ReadPendingException");
                }

                // Client có thể GHI khi read của chính nó đang chờ.
                writeAll(client, StandardCharsets.UTF_8.encode("ping"));

                String serverReceived = StandardCharsets.UTF_8.decode(
                        readExactly(server, 4)).toString();

                writeAll(server, StandardCharsets.UTF_8.encode("pong"));

                int first = pendingRead.get(3, TimeUnit.SECONDS);
                if (first < 0) {
                    throw new EOFException("No response");
                }
                while (response.position() < 4) {
                    int n = client.read(response).get(3, TimeUnit.SECONDS);
                    if (n < 0) {
                        throw new EOFException("Truncated response");
                    }
                }
                response.flip();

                System.out.println("Second read rejected: "
                        + rejectedSecondRead);
                System.out.println("Server received: " + serverReceived);
                System.out.println("Client received: "
                        + StandardCharsets.UTF_8.decode(response));
                System.out.println("Read and write overlapped: true");
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 OneReadOneWriteDemo.java
java OneReadOneWriteDemo
~~~

**Stdout trên môi trường TCP loopback hoạt động bình thường:**

~~~text
Second read rejected: true
Server received: ping
Client received: pong
Read and write overlapped: true
~~~

Phân tích chi tiết:

- `listener.accept()` và `client.connect(...)` được bắt đầu bất đồng bộ; kết quả của chúng được lấy bằng `Future.get()` để code demo ngắn và có thứ tự rõ ràng.
- `pendingRead` giữ chỗ **đọc của client**. Vì server chưa gửi dữ liệu, read chưa thể hoàn tất. Do đó thử `client.read(ByteBuffer.allocate(4))` lần thứ hai bị từ chối bằng `ReadPendingException`.
- `writeAll(client, "ping")` dùng **hướng ghi**, vẫn được phép dù read của client đang pending. Đây chính là ý nghĩa TCP full-duplex trên một `AsynchronousSocketChannel`.
- `writeAll` lặp khi `src.hasRemaining()` để xử lý **partial write**. Nó luôn chờ write trước hoàn thành rồi mới khởi tạo write kế tiếp; không tự tạo hai writes pending.
- `readExactly` đọc tới đúng số byte cần thiết, luôn đợi read trước hoàn thành rồi mới bắt đầu read kế. TCP là byte stream; 4 byte có thể đến qua nhiều completion.
- Sau khi `pendingRead.get(...)` trả về, read trước đã xong. Nếu mới đọc được một phần `"pong"`, code mới gọi tiếp `client.read(...)`. Lúc ấy không còn read đang outstanding, nên hợp lệ.
- Chương trình không cố tình tạo hai writes pending, vì một write nhỏ có thể hoàn tất quá nhanh để tái tạo lỗi đó đáng tin.
- Một `get(timeout)` hết thời gian sẽ dẫn tới exception và khối try-with-resources đóng channels. Ví dụ này không nên được hiểu là một giao thức production xử lý mọi lỗi mạng.

## 6. Tại sao “gọi write hai lần liên tục” không phải unit test chắc chắn?

Xét code:

~~~java
Future<Integer> first = channel.write(bufferA);
Future<Integer> second = channel.write(bufferB);
~~~

Trên một kết nối TCP có khả năng ghi nhanh, `first` có thể **đã hoàn tất** trước khi lời gọi thứ hai diễn ra. Khi ấy hai write không còn overlap nên lần thứ hai **có thể hợp lệ**. Ngược lại, nếu `first` vẫn pending, lời gọi write thứ hai ném `WritePendingException`.

Vì vậy:
- Đừng khẳng định đoạn code này **luôn** ném exception.
- Đừng cho rằng đoạn code này **luôn** an toàn khi chạy trên máy thử nhanh.
- Đừng dùng `Thread.sleep(10)` để “đồng bộ” hai writes; timing phụ thuộc OS, CPU, socket buffer, scheduler và kích thước payload.
- Đừng để lỗi xuất hiện rồi retry trong vòng lặp bận. Pending exception là **tín hiệu ứng dụng đã vi phạm thứ tự submit**, không phải một cách điều tiết tốc độ network hiệu quả.

Nếu nhiều producer có dữ liệu cần gửi, cho từng producer **enqueue** vào một output queue có giới hạn. Một writer logic duy nhất sở hữu quyền gọi `channel.write(...)` cho mỗi channel và chỉ submit lần kế khi lần trước **hoàn tất**.

## 7. Cách serialize writes: chỉ một writer operation, nhưng nhiều messages

Mô hình đơn giản cho một connection:

~~~text
Producer A ----\
Producer B -----+--> per-connection output queue
Producer C ----/                 |
                                  v
                          writer state machine
                                  |
                         [no write pending?]
                           /             \
                         YES             NO
                          |               |
                          v               v
                     poll buffer      giữ trong queue
                          |
                      channel.write()
                          |
                         pending
                          |
                 completed/failed callback
                          |
                buffer.hasRemaining() ?
                  /               \
                YES               NO
                 |                 |
          write phần còn       lấy buffer kế tiếp
          thiếu (sau khi       nếu queue chưa rỗng
          completion)
~~~

**Bất biến (invariant)** nên giữ:

1. **Một write đang in-flight** trên mỗi channel; các message khác ở queue của ứng dụng, không tự gọi `channel.write` song song.
2. Buffer đang được write **không bị sửa bởi producer**. Producer chỉ chuyển quyền sở hữu buffer vào queue sau khi chuẩn bị (ví dụ `flip()`).
3. Khi callback write xong, nếu buffer còn byte thì submit write mới cho **cùng buffer** sau khi thao tác trước hoàn thành.
4. Chỉ khi buffer hiện tại hết byte, lấy buffer tiếp theo từ queue.
5. Nếu queue/pending bytes vượt ngưỡng, tạm dừng producer hoặc từ chối request. Không cho queue tăng vô hạn vì client đọc chậm.
6. Nếu có exception hoặc channel đóng, **dừng phát tiếp** và hoàn tất/cancel các promise ở ứng dụng theo chính sách đã định.

Ví dụ **snippet ở bên trong một hàm callback đã có connection state**, không phải chương trình độc lập:

~~~java
private void writeNext(ByteBuffer pending) {
    channel.write(pending, pending,
            new CompletionHandler<Integer, ByteBuffer>() {
        @Override
        public void completed(Integer n, ByteBuffer buffer) {
            if (buffer.hasRemaining()) {
                // Write trước ĐÃ complete: bây giờ được gọi write kế.
                writeNext(buffer);
            } else {
                // Lấy buffer tiếp theo từ output queue nếu có.
                drainNextQueuedBuffer();
            }
        }

        @Override
        public void failed(Throwable exc, ByteBuffer buffer) {
            failAndCloseConnection(exc);
        }
    });
}
~~~

Snippet này **giả định** `channel`, `drainNextQueuedBuffer()`, `failAndCloseConnection()` là các thành viên của connection-state owner và queue đã được đồng bộ; tên method để minh họa flow, không phải API Java chuẩn. Khi ứng dụng dùng callbacks có thể chạy ở nhiều thread, việc chuyển từ “đang ghi” sang “lấy phần tử queue tiếp theo” phải được **serialize/synchronize**; đơn thuần có queue thread-safe không đủ nếu hai producer cùng thấy `writing == false` rồi đều gọi `write`.

Một số cách triển khai:
- Event loop/actor per connection nhận lệnh enqueue và chỉ event-loop thread gọi write.
- Một lock ngắn bảo vệ `writingFlag` và queue, tránh giữ lock suốt khi I/O chờ.
- Một state machine dùng atomic flag và một queue bounded, với các chuyển trạng thái được kiểm chứng chống lost wakeup.

Đây là điều phối ở **tầng ứng dụng** để tuân thủ giới hạn của channel, chứ không phải cơ chế tự động queue writes của `AsynchronousSocketChannel`.

## 8. CompletionHandler: lập lịch lần đọc kế tiếp sau khi lần hiện tại hoàn thành

Với server đọc stream nhiều lần, nguyên tắc là **chain read** trong completion thay vì gọi liên tiếp trước khi có kết quả. Đối với giao thức có độ dài biết trước, đoạn handler cần xử lý cả partial read và EOF.

Chương trình dưới dùng callback để nhận đúng 4 byte. Mỗi lần `completed` có dữ liệu nhưng buffer chưa đủ, handler **lập lịch lại đọc**. Callback chỉ submit lần tiếp sau khi lần trước hoàn thành, nên không vi phạm giới hạn pending.

Tạo file **`CallbackReadDemo.java`**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class CallbackReadDemo {
    static void writeAll(AsynchronousSocketChannel ch, ByteBuffer data)
            throws Exception {
        while (data.hasRemaining()) {
            if (ch.write(data).get(3, TimeUnit.SECONDS) < 0) {
                throw new EOFException("Write failed");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open();
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {

            listener.bind(new InetSocketAddress("127.0.0.1", 0));
            Future<AsynchronousSocketChannel> accepting = listener.accept();
            client.connect(listener.getLocalAddress())
                    .get(3, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel server =
                         accepting.get(3, TimeUnit.SECONDS)) {

                CountDownLatch done = new CountDownLatch(1);
                AtomicReference<String> received = new AtomicReference<>();
                AtomicReference<Throwable> error = new AtomicReference<>();
                ByteBuffer buffer = ByteBuffer.allocate(4);

                CompletionHandler<Integer, ByteBuffer> handler =
                        new CompletionHandler<>() {
                    @Override
                    public void completed(Integer n, ByteBuffer dst) {
                        if (n == -1) {
                            failed(new EOFException("Early EOF"), dst);
                        } else if (dst.hasRemaining()) {
                            server.read(dst, dst, this);
                        } else {
                            dst.flip();
                            received.set(
                                    StandardCharsets.UTF_8.decode(dst)
                                            .toString());
                            done.countDown();
                        }
                    }

                    @Override
                    public void failed(Throwable cause, ByteBuffer dst) {
                        error.set(cause);
                        done.countDown();
                    }
                };

                server.read(buffer, buffer, handler);
                writeAll(client, StandardCharsets.UTF_8.encode("ping"));

                if (!done.await(3, TimeUnit.SECONDS)) {
                    throw new IOException("Timed out waiting for callback");
                }
                if (error.get() != null) {
                    throw new IOException("Read failed", error.get());
                }

                System.out.println("Callback received: " + received.get());
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CallbackReadDemo.java
java CallbackReadDemo
~~~

**Stdout nếu TCP loopback hoạt động:**

~~~text
Callback received: ping
~~~

Để demo tự kết thúc, `CountDownLatch` chỉ được dùng trong **main** để chờ handler; chính handler không gọi `Future.get()` và không chặn để đợi một I/O khác. `AtomicReference` lưu kết quả/error cho thread main và `countDown()` phát tín hiệu hoàn tất.

Đối với một server thật, có thể dùng callback để nối vòng đời đọc/parse/ghi liên tục, nhưng phải áp dụng framing, giới hạn buffer, idle timeout, error handling và backpressure. Tham số attachment `dst` gắn đúng buffer với read operation. Không dùng buffer ấy ở thread khác trong khi pending.

**Lưu ý handler callback:** Sau khi callback của lần read trước được gọi, việc khởi tạo read kế tiếp phù hợp với mô hình chaining; nhưng trong application có nhiều producer/callback cùng sửa trạng thái, vẫn phải sở hữu buffer và serialize state transitions.

## 9. Partial read, partial write và TCP framing

Giới hạn một operation đang chờ **không hề** đảm bảo một lần completion tương đương một message ứng dụng.

**TCP truyền byte stream:**
- Một lần `write(100 bytes)` ở client không bắt buộc tương ứng một lần `read(100 bytes)` ở server.
- Một lần read có thể nhận 1 byte, 100 bytes hoặc nhiều message dính liền nhau nếu buffer đủ.
- Một lần write có thể hoàn thành với `n < src.remaining()` ban đầu, dù không có lỗi.
- Đọc được `-1` nghĩa là peer đã kết thúc luồng input (EOF), không có nghĩa gói ứng dụng rỗng.
- Một lần ghi completed có nghĩa dữ liệu đã được chuyển khỏi application buffer theo socket I/O contract, **không chứng minh remote application đã nhận và xử lý**.

Vì thế cần hai mức tổ chức:

| Tầng | Trách nhiệm |
| --- | --- |
| I/O scheduling | Đảm bảo ≤1 read pending, ≤1 write pending cho mỗi channel |
| Protocol framing | Xác định khi nào đủ một message, ví dụ length-prefix, delimiter, fixed size; kiểm tra kích thước, encoding |

Với message dài biến đổi, có thể dùng 4-byte length header trong network byte order:
1. Đọc cho đủ **header**; parse kích thước an toàn.
2. Kiểm tra độ dài với giới hạn ứng dụng trước khi cấp buffer.
3. Đọc cho đủ payload, có thể qua nhiều async read completions.
4. Decode/dispatch message.
5. Nếu dữ liệu mới đang chờ, tiếp tục read theo state machine.

Không viết handler kiểu:

~~~java
// SAI nếu coi một lần hoàn thành read là một request đầy đủ.
channel.read(buffer, null, new CompletionHandler<>() {
    @Override
    public void completed(Integer n, Object ignored) {
        processOneFullRequest(buffer); // Chưa biết đã đủ frame chưa.
    }
    @Override
    public void failed(Throwable error, Object ignored) {
        closeConnection();
    }
});
~~~

Đây là **mã phản ví dụ**, không phải chương trình hoàn chỉnh; `processOneFullRequest` và `closeConnection` chỉ biểu diễn lỗi thiết kế. Cần parser state và kiểm tra `n`/EOF trước khi dispatch. Nếu UTF-8 code point bị tách giữa nhiều reads, dùng decoder có trạng thái hoặc chỉ decode khi đã có frame hoàn chỉnh.

## 10. ByteBuffer ownership và dữ liệu đồng thời

Ngay cả khi chỉ có một read và một write, vẫn có thể phát sinh **data race** nếu hai operation cùng dùng một `ByteBuffer`:

~~~java
// RỦI RO: hai I/O operations có thể sửa cùng buffer.position.
ByteBuffer shared = ByteBuffer.allocate(1024);
Future<Integer> reading = channel.read(shared);
Future<Integer> writing = channel.write(shared);
~~~

Read và write của channel là **hai hướng hợp lệ**, nhưng ByteBuffer `shared` là đối tượng mutable, không an toàn khi được hai I/O thao tác đồng thời; `position` và bytes có thể thay đổi khi provider thực thi I/O.

Mẫu đúng cho full-duplex:

~~~java
ByteBuffer inbound = ByteBuffer.allocate(8192);
ByteBuffer outbound = ByteBuffer.wrap(responseBytes);

Future<Integer> readFuture = channel.read(inbound);
Future<Integer> writeFuture = channel.write(outbound);
~~~

Đây là snippet với `responseBytes` là mảng byte riêng đã chuẩn bị. Mỗi operation sở hữu buffer riêng cho đến khi completion. Ngay cả với mảng khác nhau, **đừng sửa** nội dung `outbound` khi write chưa complete, hoặc đọc/sửa `inbound` trong lúc read chưa complete.

Khi đọc hoàn tất:
- Có `n > 0`, vị trí buffer đã tiến lên `n`.
- Dùng `flip()` để chuyển sang đọc phần đã nhận; chỉ làm **sau completion**.
- Khi parse chưa hết bytes, dùng `compact()` để giữ phần dư, và chỉ submit read mới khi buffer ở write mode.
- Không gọi `clear()` rồi ghi đè dữ liệu còn cần parser hoặc in-flight write.
- Có thể copy dữ liệu ra immutable message trước khi giao cho worker CPU/DB.

Đối với write đang pending, giữ cùng `ByteBuffer` đến completion; sau khi phần đã ghi xong, `hasRemaining()` quyết định phải ghi tiếp hay có thể lấy message khác.

## 11. Timeout: phân biệt chờ Future với timeout của I/O operation

Đây là khác biệt đặc biệt quan trọng cho trạng thái “đang chờ”:

| Cơ chế | Ví dụ | Khi hết thời gian | Tác động tới pending slot |
| --- | --- | --- | --- |
| **Timeout khi chờ Future** | `future.get(1, SECONDS)` | Thread đang chờ nhận `TimeoutException` | **Không tự kết thúc** I/O; operation có thể vẫn pending |
| **I/O timeout ở overload callback** | `channel.read(dst, 1, SECONDS, state, handler)` | Operation hoàn tất thất bại qua `InterruptedByTimeoutException` | Có thể để channel/dữ liệu ở trạng thái lỗi do provider quyết định |
| **Đóng channel** | `channel.close()` | Kết thúc vòng đời channel, pending I/O được xử lý thất bại/cancel theo contract và provider | Không tiếp tục dùng channel đã đóng |

Một lỗi phổ biến:

~~~java
Future<Integer> first = channel.read(dst);
try {
    first.get(1, TimeUnit.SECONDS);
} catch (TimeoutException e) {
    // SAI: first có thể vẫn pending, read tiếp sẽ ReadPendingException.
    channel.read(otherDst);
}
~~~

Đây là **snippet phản ví dụ** (cần khai báo/import đầy đủ), không phải cách khuyến nghị.

Nếu không thể chờ lâu hơn, hãy định nghĩa **lifecycle policy**: có thể đóng connection để giải phóng tài nguyên và mở channel khác khi cần; không khởi tạo cùng một thao tác trên channel chưa biết đã sạch pending hay chưa. Khi ứng dụng dùng `Future.cancel(...)`, không được chỉ dựa vào trạng thái Future đã cancelled để suy ra byte buffer/chuyển trạng thái của channel luôn an toàn; theo dõi contract của channel, provider và đóng connection khi không chắc trạng thái.

**Cảnh báo với I/O timeout thật:** Javadoc `AsynchronousSocketChannel` nêu rằng timeout có thể khiến channel hoặc underlying connection ở trạng thái không nhất quán. Khi provider không bảo đảm dữ liệu đã/không được chuyển, các read/write về sau có thể bị từ chối bằng runtime exception không xác định cụ thể; trạng thái của `ByteBuffer` sau I/O timeout có thể **không được định nghĩa**. Đối với giao thức đòi hỏi tính đúng đắn, thường nên **đóng connection và bỏ các buffers liên quan** thay vì retry trên cùng channel như không có gì xảy ra.

Với overload timeout, giá trị timeout **≤0** được Java API hiểu là không timeout cho I/O operation, khác hẳn `Future.get(0, unit)` với ý nghĩa “chỉ chờ tối đa 0 đơn vị thời gian” ở tầng Future.

## 12. Cancellation, close và error handling

Những lỗi thường gặp trong code async:

| Exception / trạng thái | Ý nghĩa | Chiến lược |
| --- | --- | --- |
| `ReadPendingException` | Đã có read outstanding trên channel | Không submit thêm; chờ completion, sửa read state |
| `WritePendingException` | Đã có write outstanding trên channel | Enqueue output, serialize writes theo connection |
| `NotYetConnectedException` | Gọi read/write trước khi TCP channel kết nối xong | Chờ connect Future/callback complete |
| `ConnectionPendingException` | Gọi connect mới khi connect trước còn pending | Chỉ một connect flow cho channel |
| `InterruptedByTimeoutException` | I/O callback operation vượt timeout | Bỏ buffer nghi ngờ, đóng/recreate channel theo policy |
| `AsynchronousCloseException` / `ClosedChannelException` | Channel đóng khi đang thao tác hoặc trước khi khởi tạo | Cleanup state và đừng tiếp tục submit |
| `ExecutionException` từ `Future.get()` | I/O future hoàn tất thất bại | Kiểm tra `getCause()`, xử lý lỗi gốc |
| `TimeoutException` từ `Future.get(timeout)` | Caller chờ quá thời gian | Operation có thể còn pending; không submit trùng |
| `CancellationException` | Future đã bị cancel | Không mặc định data transfer hoặc buffer đã được hoàn nguyên |
| `n == -1` khi read | EOF, phía đối diện đã kết thúc luồng input | Xử lý shutdown/half-close/close theo protocol |

**Đóng channel** trong `try-with-resources` hoặc explicit cleanup là cách rõ ràng để kết thúc vòng đời. Trong hệ thống thật, khi connection bị hỏng nên:
1. Đánh dấu state thành CLOSED.
2. Không nhận thêm read/write requests cho channel đó.
3. Đóng channel.
4. Hoàn tất các future/promises hoặc callback nghiệp vụ còn chờ bằng lỗi có ngữ cảnh.
5. Hủy/giải phóng output queue và buffers chỉ khi không còn I/O ghi vào chúng; nếu provider báo trạng thái buffer không xác định sau timeout, không tái sử dụng tùy tiện.

**Không nuốt exception pending rồi gọi lại ngay trong vòng while**. Nếu một event-handler xuất hiện `WritePendingException` liên tục thì lỗi nằm ở **scheduling/state machine**, không nhất thiết do mạng quá tải.

## 13. Không nhầm với AsynchronousServerSocketChannel và AsynchronousFileChannel

Mặc dù tên đều bắt đầu bằng “Asynchronous”, mỗi API có giới hạn riêng:

- `AsynchronousSocketChannel`: một read pending và một write pending, **hai hướng có thể chồng nhau**.
- `AsynchronousServerSocketChannel`: dùng `accept()` để nhận connection; một lần accept đang chờ không đồng nghĩa read/write trên client channel. Lớp này cũng giới hạn **một accept pending** và có `AcceptPendingException` nếu bắt đầu accept mới khi accept trước chưa hoàn tất.
- `AsynchronousFileChannel`: thao tác read/write tại vị trí file cụ thể, không áp dụng giản đơn cùng giới hạn pending socket ở đây; xem Javadoc của lớp khi thiết kế concurrency.
- `SocketChannel` trong NIO non-blocking dùng `Selector` và readiness để điều phối; `AsynchronousSocketChannel` dùng Future/callback completion. Hai mô hình đều có thể xử lý nhiều kết nối nhưng **không dùng cùng API**.
- `AsynchronousChannelGroup` quản lý nguồn thực thi callback/thành viên channel, **không làm tăng số read/write pending cho một socket**. Số worker threads của group không phải số I/O outstanding mỗi channel.

Điều này giúp chọn đúng công cụ:
- Cần hiểu khi nào socket **ready** để thực hiện I/O → nghiên cứu `Selector`.
- Cần khởi tạo I/O và nhận **completion** qua `Future`/`CompletionHandler` → dùng `AsynchronousSocketChannel`.
- Cần xử lý nhiều writes cùng lúc trên một connection → dùng **output queue và một writer state machine**, không mở thêm threads để “ép” channel chấp nhận nhiều writes outstanding.

## 14. Vận hành trên server có nhiều kết nối

Một server bất đồng bộ phục vụ nhiều clients nên quản lý **state per-connection**:

~~~text
acceptor
   |
   +--> client A  [readPending?] [writePending?] [output queue]
   |
   +--> client B  [readPending?] [writePending?] [output queue]
   |
   +--> client C  [readPending?] [writePending?] [output queue]
   |
   +--> ...

Mỗi client có thể:
   - tối đa 1 read pending
   - tối đa 1 write pending
   - nhiều messages QUEUED ở tầng ứng dụng (có giới hạn)
~~~

Để hiệu quả và đúng đắn:
- Sở hữu rõ operation state và buffer per connection.
- Để read callback chỉ re-arm khi muốn nhận thêm dữ liệu và khi có capacity/backpressure.
- Để write callback rút queue theo thứ tự giao thức và chỉ submit lần tiếp sau completion.
- Dùng bounded queue, high/low-water marks; ngừng nhận input hoặc từ chối yêu cầu khi output producer nhanh hơn peer đọc.
- Khi work CPU hoặc database blocking kéo dài, chuyển sang executor có giới hạn; **không** chặn những callback threads đang phục vụ nhiều channels.
- Khi response hoàn tất, xử lý half-close, flush và close đúng thứ tự; không bỏ dữ liệu còn pending.
- Đặt timeout và policy cho idle connections, phân loại lỗi theo connection thay vì làm sập cả server.
- Log số pending reads/writes, queue depth và byte counts để chẩn đoán slow client hoặc memory pressure.

Nếu một server có 1000 `AsynchronousSocketChannel`, không có nghĩa chỉ được có một read cho cả server: mỗi channel độc lập có thể chờ một read và một write. Cũng không có nghĩa 1000 operations được hoàn tất tức thì; tốc độ phụ thuộc scheduler, executor/group, OS, network và tốc độ peer.

## 15. Các lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `read` hai lần khi lần đầu chưa xong | `ReadPendingException` | Theo dõi read-in-flight, chỉ re-arm sau completion |
| Gọi `write` từ hai producers cùng lúc | `WritePendingException` khi writes overlap | Output queue + một writer logic |
| Tưởng read pending cấm write | Bỏ phí khả năng full-duplex của TCP | Cho phép một read và một write cùng tồn tại, dùng buffers riêng |
| Tưởng mỗi call write luôn pending đủ lâu | Test flaky, lỗi chỉ xảy ra trên mạng chậm | Test scheduling/state thay vì timing |
| Dùng chung một `ByteBuffer` cho read và write | Race ở position/bytes | Tách buffer và ownership |
| Gọi `flip()/clear()` trước khi I/O hoàn tất | Dữ liệu sai hoặc mất | Chỉ thao tác buffer sau completion |
| Một Future xong là một full message | TCP có partial I/O | Tích lũy đủ frame theo protocol |
| `Future.get(timeout)` bị hiểu là hủy I/O | Read/write có thể còn pending | Quy định policy timeout/close rõ ràng |
| Retry trên channel sau async I/O timeout như bình thường | Buffer/connection có thể không nhất quán | Đóng/recreate, không tái sử dụng dữ liệu nghi ngờ |
| Không quản lý EOF `-1` | Tiếp tục read vô hạn/đóng muộn | Xử lý half-close và lifecycle |
| Không giới hạn output queue | Slow clients có thể gây OOM | Backpressure/queue size bound |
| Chờ `Future.get()` trong mọi callback | Có thể block completion threads | Chain callbacks hoặc offload logic |
| Giả định callbacks luôn chạy một thread | Races trên connection state | Serialize state transitions |
| Gọi read/write khi chưa connected | `NotYetConnectedException` | Chỉ I/O sau connect completed |
| Tưởng tăng threads trong AsyncChannelGroup cho phép hai writes | Vi phạm API contract | Chỉ một writer pending bất kể thread count |

## 16. Bài tập tự kiểm tra

**1.** Một channel đang chờ `read()`, có thể gọi `write()` ngay không?  
**Đáp án:** Có, nếu chưa có write khác outstanding và channel hợp lệ. Một read cùng một write được phép overlap.

**2.** Nếu hai thread gọi `read()` đồng thời trên cùng một `AsynchronousSocketChannel`, kết quả?  
**Đáp án:** Không thể có hai reads outstanding; một lời gọi có thể ném `ReadPendingException` nếu read còn lại chưa hoàn tất.

**3.** Hai kênh A và B cùng có read pending có hợp lệ không?  
**Đáp án:** Có. Giới hạn áp dụng **theo channel**, không phải theo toàn JVM hay AsyncChannelGroup.

**4.** Tại sao lệnh `write()` thứ hai đôi khi không ném `WritePendingException`?  
**Đáp án:** Write đầu có thể hoàn thành trước lời gọi thứ hai. Exception chỉ phát sinh nếu writes thực sự overlap.

**5.** `Future.get(1, SECONDS)` ném `TimeoutException` có nghĩa thao tác đọc đã timeout và slot rỗng không?  
**Đáp án:** Không. Caller hết thời gian chờ nhưng operation có thể vẫn outstanding.

**6.** Có nên sửa `ByteBuffer.position()` khi async read đang pending không?  
**Đáp án:** Không. Buffer thuộc về I/O operation cho đến completion.

**7.** `writeFuture.get() == 4` chứng minh peer đã xử lý 4 byte không?  
**Đáp án:** Không. Chỉ có kết quả thao tác write của local channel; nhận/xử lý ở peer là tầng khác.

**8.** Callback nhận 2/4 byte của frame thì làm gì tiếp?  
**Đáp án:** Giữ buffer/parser state, re-arm một read **sau khi read trước hoàn thành**, tiếp tục tới khi đủ frame hoặc EOF/error.

**9.** Server có 100 channel thì tối đa bao nhiêu reads pending theo contract này?  
**Đáp án:** Tối đa một read đang chờ trên **mỗi** channel, nên về mặt giới hạn mỗi-channel có thể có tới 100 reads outstanding; giới hạn tài nguyên thực tế còn tùy provider/OS.

**10.** Khi cần gửi mười message trong cùng một connection nhưng chỉ có một write pending, thiết kế nào phù hợp?  
**Đáp án:** Bounded output queue với một writer state machine, xử lý partial writes và submit buffer tiếp theo sau completion.

## Tham khảo chính thức

- [Java SE 17 — AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): giới hạn tối đa một read và một write outstanding, Future/CompletionHandler, timeout, nhóm ngoại lệ.
- [Java SE 17 — AsynchronousByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousByteChannel.html): semantics read/write, ByteBuffer ownership và Future methods.
- [Java SE 17 — ReadPendingException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ReadPendingException.html) và [WritePendingException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/WritePendingException.html): khi operation cùng loại đã outstanding.
- [Java SE 17 — CompletionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): callbacks hoàn thành/thất bại.
- [Java SE 17 — AsynchronousServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): pending accept và lifecycle phía server.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): position/limit/flip/compact, ranh giới sở hữu dữ liệu.
