# Java 7 — Kênh mạng bất đồng bộ: Trạng thái đọc ghi đang chờ và giới hạn truy cập bộ đệm

## 1. Bài toán thực tế

Một server Java sử dụng `AsynchronousSocketChannel` có thể gọi `read(buffer)` và nhận về `Future<Integer>` **trước khi** có byte nào từ client. Lúc đó lần đọc **đang chờ** (*outstanding/pending operation*). Nếu code lập tức khởi tạo một lần đọc thứ hai trên **cùng socket channel**, Java có thể ném:

```text
java.nio.channels.ReadPendingException
```

Nếu chương trình gửi tiếp một lệnh ghi mới trong khi lần ghi trước chưa hoàn tất, ngoại lệ tương ứng là:

```text
java.nio.channels.WritePendingException
```

Đây **không phải** “channel chỉ có một thread được truy cập”: `AsynchronousSocketChannel` được thiết kế an toàn để nhiều thread sử dụng, nhưng hợp đồng của nó giới hạn **tối đa một lần đọc đang chờ và tối đa một lần ghi đang chờ** trên mỗi channel. **Một lần đọc và một lần ghi có thể cùng đang chờ** — đó là đặc điểm *full-duplex* hữu ích với TCP.

Song song đó, `ByteBuffer` truyền cho thao tác bất đồng bộ cần được bảo vệ: **không đọc/ghi/thay đổi trạng thái của buffer đó cho đến khi thao tác I/O hoàn thành**. Nếu caller `flip()`, `clear()`, `put()` hoặc tái sử dụng buffer trong lúc read/write vẫn pending, chương trình có thể nhận dữ liệu sai hoặc gây race giữa các thread.

Bài này thuộc **Kênh mạng bất đồng bộ** (Java NIO.2), tập trung đúng hai nội dung:

- **Trạng thái đọc/ghi đang chờ**: quy tắc một read + một write, `ReadPendingException`, `WritePendingException`, thêm `AcceptPendingException` trên listener và quản lý completion.
- **Giới hạn truy cập bộ đệm**: ownership của `ByteBuffer` trước, trong và sau operation; `position/limit`, partial transfer, timeout/cancel, liên kết với callback, pooling và lỗi concurrency.

Các API này có từ Java 7 và **vẫn áp dụng trên Java 17+**. Ví dụ hoàn chỉnh biên dịch theo `--release 17`; không sử dụng lớp nội bộ JDK hoặc kiến thức legacy.

## 2. Các thành phần NIO.2 cần biết

| API | Vai trò |
| --- | --- |
| `AsynchronousServerSocketChannel` | Đăng ký lắng nghe TCP và chấp nhận kết nối bằng asynchronous `accept` |
| `AsynchronousSocketChannel` | Kết nối TCP, thực hiện async `connect`, `read`, `write` |
| `AsynchronousByteChannel` | Interface chuẩn hóa asynchronous byte read/write |
| `Future<V>` | Đại diện kết quả thao tác chưa/đã hoàn thành; `get()` có thể chặn |
| `CompletionHandler<V,A>` | Callback `completed(result,attachment)` / `failed(error,attachment)` |
| `ByteBuffer` | Vùng nhớ nhận byte hoặc cung cấp byte; quản lý position/limit |
| `ReadPendingException` | Thử bắt đầu read khi **read trước vẫn pending** trên socket |
| `WritePendingException` | Thử bắt đầu write khi **write trước vẫn pending** trên socket |
| `AcceptPendingException` | Thử bắt đầu accept khi **accept trước vẫn pending** trên listener |
| `InterruptedByTimeoutException` | Lỗi khi timeout của asynchronous socket read/write **bên trong API** hết hạn |
| `AsynchronousChannelGroup` | Nhóm các asynchronous channels với thread pool / lifecycle liên quan |

**Lưu ý:** `AsynchronousSocketChannel` là **completion-based**. Nó không phải `SocketChannel.configureBlocking(false)` với `Selector`. `Selector` báo *readiness*; Future/CompletionHandler báo *completion* của một thao tác đã yêu cầu.

## 3. “Pending” có nghĩa gì?

Một thao tác đang pending khi đã khởi tạo nhưng **chưa hoàn tất** (thành công hoặc thất bại).

```text
                  channel.read(buffer)
                         │
                         ▼
                  READ đang pending
                   /           \
         dữ liệu đến             lỗi/đóng/timeout
               │                       │
               ▼                       ▼
        hoàn thành read          hoàn thành lỗi
               │                       │
               └────────┬──────────────┘
                        ▼
              thao tác read cũ kết thúc
                        │
            lúc này mới gửi read tiếp
```

Trong khi read đang pending:

- Có thể có **một write khác** đang pending trên **cùng socket**, theo hợp đồng.
- Không được gửi **read thứ hai** trên cùng socket; có thể ném `ReadPendingException`.
- Buffer dành cho read **thuộc về operation** cho đến khi read hoàn thành; caller không được tự đụng đến buffer đó.
- `Future.isDone() == false` cho thấy một Future vẫn chưa hoàn thành. `isDone() == true` không có nghĩa thao tác thành công: Future cũng có thể hoàn tất do lỗi hoặc hủy.
- Khi dùng callback, một lượt read kết thúc khi handler nhận sự kiện completed/failed tương ứng. Có thể khởi tạo read tiếp từ handler **sau khi thao tác cũ đã hoàn thành**.

**Không đồng nhất pending operation với “một request HTTP/TCP application đang chờ hoàn tất”.** TCP là byte stream: một logical message có thể cần nhiều lần read sau nhau, còn một read có thể nhận ít hơn số byte mà protocol yêu cầu.

## 4. Giới hạn chính xác của AsynchronousSocketChannel

Javadoc Java SE 17 nói rõ:

> Một socket channel cho phép đồng thời đọc và ghi, nhưng chỉ một read và một write outstanding tại một thời điểm.

Phân tích thành ma trận:

| Channel/operation đang pending | Gửi operation tiếp | Kết quả |
| --- | --- | --- |
| Không có read | `read(...)` | Có thể bắt đầu read |
| Đã có read chưa xong | `read(...)` | `ReadPendingException` |
| Đã có read chưa xong | `write(...)` | **Được phép** bắt đầu một write |
| Không có write | `write(...)` | Có thể bắt đầu write |
| Đã có write chưa xong | `write(...)` | `WritePendingException` |
| Đã có write chưa xong | `read(...)` | **Được phép** bắt đầu một read |
| Read và write đều đang pending | Read thứ hai hoặc write thứ hai | Bị từ chối theo loại pending tương ứng |

Một connection có **hai “slot” I/O độc lập**: một slot đọc, một slot ghi. Đây không phải hai semaphore đếm toàn hệ thống; **mỗi instance `AsynchronousSocketChannel` có giới hạn riêng**. Nhiều socket khác nhau có thể đang xử lý các read/write khác nhau cùng lúc.

### 4.1. Khi nào ném ReadPendingException?

Ví dụ minh họa trên một `AsynchronousSocketChannel channel` **đã kết nối**:

```java
ByteBuffer firstBuffer = ByteBuffer.allocate(1024);
Future<Integer> first = channel.read(firstBuffer);

// Nếu first vẫn pending, lệnh này sẽ ném ReadPendingException:
Future<Integer> second = channel.read(ByteBuffer.allocate(1024));
```

Đây là **snippet minh họa**, không phải test độc lập có kết quả luôn giống nhau. Nếu read đầu **đã hoàn thành** trước lần read thứ hai, lệnh thứ hai có thể thành công. Muốn test `ReadPendingException` có tính quyết định, phải kiểm soát rằng peer **chưa gửi dữ liệu** và read thứ nhất thực sự pending.

### 4.2. Khi nào ném WritePendingException?

```java
ByteBuffer firstBuffer = ByteBuffer.wrap(bigPayload);
Future<Integer> first = channel.write(firstBuffer);

// Nếu first vẫn pending, write thứ hai sẽ ném WritePendingException:
Future<Integer> second = channel.write(ByteBuffer.wrap(otherPayload));
```

Đây là **snippet minh họa** có `channel` đã kết nối và hai `byte[] bigPayload/otherPayload`. Nó không phải một test bảo đảm `WritePendingException` trên mọi hệ thống: TCP có thể chấp nhận một lần ghi nhỏ rất nhanh, khiến write đầu đã hoàn thành. **Không tăng dung lượng bộ nhớ vô hạn để cố ép socket backlog** chỉ nhằm tạo ngoại lệ; trong unit test, nên kiểm soát scheduling hoặc dùng mock/abstraction có pending-write state.

### 4.3. Pending là thuộc tính của thao tác, không phải của ByteBuffer

Dùng **hai buffer khác nhau** cho hai read **không vượt qua** giới hạn một outstanding read:

```java
channel.read(bufferA);
channel.read(bufferB); // ReadPendingException nếu A chưa xong.
```

Vấn đề là **channel còn read pending**, không phải hai lệnh dùng chung buffer. Ngược lại, dùng **hai channel khác nhau** có thể cho phép hai read song song — miễn mỗi channel tuân thủ own pending limit và các buffers không được chia sẻ sai.

## 5. Giới hạn của AsynchronousServerSocketChannel: một accept

`AsynchronousServerSocketChannel` cung cấp:

```java
Future<AsynchronousSocketChannel> pending = listener.accept();
```

Nếu accept này chưa hoàn tất và code gọi `listener.accept()` lần nữa, nó ném `AcceptPendingException`. Đây là nguyên tắc **một accept đang chờ trên một listener**, tương tự giới hạn read/write trên một socket nhưng là loại operation khác.

**Ví dụ:**

```java
Future<AsynchronousSocketChannel> firstAccept = listener.accept();
try {
    listener.accept();
} catch (AcceptPendingException expected) {
    System.out.println("accept is already pending");
}
```

Đây là snippet trong phương thức với `listener` đã bind. Để ngoại lệ chắc xảy ra, phải đảm bảo chưa có client kết nối trước lần accept thứ hai. Nếu `firstAccept` hoàn thành ngay do có client đang chờ, bạn có thể bắt đầu accept khác hợp lệ.

**Không dùng “một accept” để kết luận listener chỉ xử lý một client trong suốt vòng đời.** Sau khi accept hoàn thành, có thể tạo **lần accept kế tiếp** trong khi xử lý client vừa được chấp nhận. Mỗi client được trả về là một `AsynchronousSocketChannel` riêng với giới hạn read/write của riêng nó.

## 6. Vòng đời của ByteBuffer trước, trong và sau asynchronous I/O

Một `ByteBuffer` có ba trạng thái tổ chức quan trọng:

| Giai đoạn | Ai có quyền sử dụng buffer? | Có thể làm gì? |
| --- | --- | --- |
| Trước khi gọi read/write | Caller | `allocate/wrap`, `put`, `flip`, `clear`, cấu hình position/limit |
| Sau khi khởi tạo, trước completion | Operation/provider giữ buffer | **Caller không được truy cập hoặc thay đổi buffer đó** |
| Sau khi hoàn tất và đã quan sát completion | Caller/handler | Đọc count/position, `flip`, decode, xử lý, `clear/compact`, tái sử dụng có kiểm soát |

Javadoc `AsynchronousByteChannel`/`AsynchronousSocketChannel` nêu rõ **ByteBuffers không an toàn cho truy cập từ nhiều thread đồng thời**; khi đã bắt đầu read/write, ứng dụng cần tránh đụng buffer cho đến khi operation hoàn thành.

### 6.1. Không chỉ cấm put(): cả flip(), clear() và đổi position cũng sai

Giả sử:

```java
ByteBuffer dst = ByteBuffer.allocate(1024);
Future<Integer> pending = channel.read(dst);

// SAI: đây là lúc read còn pending nếu chưa có completion:
dst.flip();
dst.clear();
dst.put((byte) 42);
```

Đây là **anti-pattern**, không phải đoạn mã hợp lệ cần chạy. Ngoài thay bytes, việc đọc các thuộc tính trạng thái như `position/remaining` từ một thread khác cũng có thể cạnh tranh với provider đang cập nhật buffer. Không có bảo đảm portable cho việc caller can thiệp vào buffer trong thời gian operation đang chờ.

### 6.2. Read: buffer ban đầu ở chế độ nhận byte

```java
ByteBuffer destination = ByteBuffer.allocate(8);
Future<Integer> operation = channel.read(destination);

// KHÔNG chạm destination cho đến khi operation hoàn thành.
int transferred = operation.get(5, TimeUnit.SECONDS);

if (transferred > 0) {
    destination.flip();
    byte[] data = new byte[transferred];
    destination.get(data);
}
```

Đây là snippet trong phương thức với imports `ByteBuffer`, `Future`, `TimeUnit` và xử lý checked exceptions. `get(timeout)` có thể chặn, nhưng sau khi trả thành công nó cho biết operation đã hoàn thành; lúc đó caller mới dùng buffer.

Nếu `operation.get(...)` ném `TimeoutException`, **không suy operation đã dừng**; không `flip/clear/reuse` buffer ngay, vì operation có thể vẫn đang chạy.

### 6.3. Write: nguồn phải được chuẩn bị để đọc byte

```java
ByteBuffer source = ByteBuffer.allocate(8);
source.put("ping".getBytes(StandardCharsets.UTF_8));
source.flip();

Future<Integer> pendingWrite = channel.write(source);
int n = pendingWrite.get(5, TimeUnit.SECONDS);

// Sau completion mới kiểm tra source.hasRemaining().
if (source.hasRemaining()) {
    // Cần gửi tiếp phần bytes còn lại, theo thứ tự protocol.
}
```

Đây là snippet trong phương thức, `channel` đã kết nối. Quên `flip()` sau `put` sẽ khiến nguồn ở vị trí cuối, dẫn tới gửi bytes không như mong muốn hoặc chỉ gửi phần remaining không đúng.

### 6.4. Position thay đổi bao nhiêu sau completion?

Theo Java API:

- Tại thời điểm read/write được thực hiện, provider dùng vùng `[position, limit)`.
- Nếu read/write chuyển **n dương** bytes, sau khi hoàn tất `buffer.position() = positionBanĐầu + n`.
- `limit()` không tự đổi vì completion.
- Với `dst.remaining() == 0`, read có thể hoàn thành ngay với **0** và không thực hiện I/O.
- Với `src.remaining() == 0`, write tương tự có thể hoàn thành với **0**.
- EOF khi đọc stream được biểu diễn bằng **-1**.

Hệ quả: **một completion không có nghĩa buffer đã đầy hoặc đã gửi hết**. Dùng chính count và `hasRemaining()` sau completion để lên lịch thao tác tiếp.

## 7. Ví dụ Java 17+ hoàn chỉnh: pending accept, pending read và full-duplex

Chương trình **`PendingSocketDemo.java`** dưới đây không cần kết nối ra Internet: tạo một listener trên **loopback**, port ngẫu nhiên do OS cấp, một client kết nối đến listener và một accepted socket.

Kiểm thử:

1. Đặt một `accept()` pending rồi cố accept thêm lần nữa → `AcceptPendingException`.
2. Khi đã kết nối, bắt đầu read trên socket được accept **trước khi client gửi byte**.
3. Cố bắt đầu read thứ hai → `ReadPendingException`.
4. Trong khi read đầu đang pending, socket được accept **vẫn write được** `pong` sang client.
5. Client nhận đủ `pong`, gửi lại `ping`. Read đầu ở server hoàn tất; buffer chỉ được đọc/flip **sau Future.get()**.
6. Client dùng `shutdownOutput()`; server đọc tiếp và nhận `-1` (EOF) sau khi đã tiêu thụ bytes.
7. Các socket/listener tự đóng bằng try-with-resources.

**Tệp: `PendingSocketDemo.java`**

```java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.AcceptPendingException;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.ReadPendingException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class PendingSocketDemo {
    private static int readExactly(AsynchronousSocketChannel channel,
                                   ByteBuffer destination,
                                   Future<Integer> first) throws Exception {
        int total = 0;
        Future<Integer> pending = first;
        while (true) {
            int n = pending.get(5, TimeUnit.SECONDS);
            if (n < 0) throw new IOException("Unexpected EOF");
            total += n;
            if (!destination.hasRemaining()) return total;
            pending = channel.read(destination);
        }
    }

    private static void writeExactly(AsynchronousSocketChannel channel,
                                     ByteBuffer source) throws Exception {
        while (source.hasRemaining()) {
            int n = channel.write(source).get(5, TimeUnit.SECONDS);
            if (n < 0) throw new IOException("Unexpected write EOF");
        }
    }

    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel listener =
                 AsynchronousServerSocketChannel.open().bind(
                     new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {

            Future<AsynchronousSocketChannel> accepting = listener.accept();
            boolean acceptPendingRejected = false;
            try {
                listener.accept();
            } catch (AcceptPendingException expected) {
                acceptPendingRejected = true;
            }

            client.connect(listener.getLocalAddress()).get(5, TimeUnit.SECONDS);
            try (AsynchronousSocketChannel peer =
                     accepting.get(5, TimeUnit.SECONDS)) {
                ByteBuffer request = ByteBuffer.allocate(4);
                Future<Integer> firstRead = peer.read(request);

                boolean secondReadRejected = false;
                try {
                    peer.read(ByteBuffer.allocate(1));
                } catch (ReadPendingException expected) {
                    secondReadRejected = true;
                }

                ByteBuffer reply = ByteBuffer.wrap(
                    "pong".getBytes(StandardCharsets.UTF_8));
                writeExactly(peer, reply);

                ByteBuffer receivedReply = ByteBuffer.allocate(4);
                int replyBytes = readExactly(client, receivedReply,
                                            client.read(receivedReply));
                receivedReply.flip();

                writeExactly(client, ByteBuffer.wrap(
                    "ping".getBytes(StandardCharsets.UTF_8)));
                int requestBytes = readExactly(peer, request, firstRead);
                request.flip();

                System.out.println("accept pending rejected = " + acceptPendingRejected);
                System.out.println("second read rejected = " + secondReadRejected);
                System.out.println("read and write overlap = " +
                    (replyBytes == 4 && requestBytes == 4));
                System.out.println("client received = " +
                    StandardCharsets.UTF_8.decode(receivedReply));
                System.out.println("server received = " +
                    StandardCharsets.UTF_8.decode(request));
                System.out.println("request total bytes = " + requestBytes);

                client.shutdownOutput();
                ByteBuffer eof = ByteBuffer.allocate(1);
                System.out.println("server EOF = " +
                    peer.read(eof).get(5, TimeUnit.SECONDS));
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 PendingSocketDemo.java
java PendingSocketDemo
```

**Stdout thực tế được kiểm thử trên Windows, JDK 24, loopback IPv4/IPv6 theo môi trường:**

```text
accept pending rejected = true
second read rejected = true
read and write overlap = true
client received = pong
server received = ping
request total bytes = 4
server EOF = -1
```

**Giải thích rõ từng kết quả:**

- `accept pending rejected = true`: listener còn `accept()` pending khi code thử accept lần hai.
- `second read rejected = true`: server socket đã bắt đầu read mà chưa có byte request; read thứ hai bị từ chối.
- `read and write overlap = true`: một read từ client và một write về client được thực hiện theo hướng **full-duplex** trên cùng server socket, với tổng byte nhận chính xác.
- Client nhận `pong` và server nhận `ping`. Không cần tin rằng một lần TCP read sẽ trả đầy đủ 4 byte; helper `readExactly` đọc lặp theo **số byte thực nhận**.
- `request total bytes = 4`: sau completion, helper nhận 4 byte rồi mới caller `flip()`/decode buffer.
- `server EOF = -1`: sau khi client shutdown output và server đã tiêu thụ hết dữ liệu request, lần read tiếp theo nhận end-of-stream.

**Điểm đặc biệt trong helper `readExactly`:** nó gọi `pending.get(...)` **trước khi** kiểm tra `destination.hasRemaining()`. Điều này đảm bảo không có thread khác đọc trạng thái ByteBuffer khi asynchronous read đầu đang pending. Sau khi operation đã hoàn tất, chương trình mới đọc trạng thái và quyết định submit read tiếp. Đây là ownership discipline trọng tâm của bài.

**Giới hạn:** Ví dụ cần quyền mở local TCP loopback và provider hỗ trợ async channels. Các timeout 5 giây chỉ phục vụ demo, không phải SLA của mọi OS. Nếu timeout, ngoại lệ được truyền và try-with-resources đóng channels; không báo thành công giả. Không dùng demo này để benchmark performance. Nó cố tình không gây WritePendingException bằng cách đẩy lượng dữ liệu lớn vào socket, vì write nhỏ trên loopback có thể hoàn thành rất nhanh; quy tắc write pending được minh họa riêng bên dưới.

## 8. Vì sao ReadPendingException dễ tái hiện hơn WritePendingException?

Trong demo, server gọi read khi **client chưa gửi byte nào**, nên có một read đang chờ dữ liệu. Lần read thứ hai xảy ra ngay khi chưa có data và có thể chắc chắn bắt được ReadPendingException.

Với write, hệ điều hành có thể nhận byte vào send buffer nhanh, dù client chưa đọc. Do đó:

```java
Future<Integer> first = channel.write(ByteBuffer.wrap(new byte[] {1, 2}));
Future<Integer> second = channel.write(ByteBuffer.wrap(new byte[] {3, 4}));
```

không phải một bài test portable bảo đảm ném WritePendingException: write đầu có thể hoàn thành **trước** write thứ hai. Nếu first vẫn pending, second bị từ chối theo hợp đồng. Nếu first đã xong, second hợp lệ.

**Cách test đúng:** tách tầng quản lý send queue (chỉ cho phép một write pending) thành logic có thể unit test bằng fake completion; integration test trên OS cụ thể kiểm tra hoạt động thực nhưng không phụ thuộc thời gian/gói TCP để tạo lỗi định kỳ. Không cố flood nhiều megabyte chỉ để làm socket write block trong test bình thường.

### 8.1. Cấu trúc đúng khi có nhiều thông điệp cần gửi

Một socket async nên có **outbound queue**:

```text
Queue(message1, message2, message3)
                  │
          writePending = false?
                  │
                  ▼
         submit write(message1)
                  │
           writePending = true
                  │
             completed(n)
                  │
       src.hasRemaining()?
          /               \
        yes                no
         │                  │
  write phần còn lại    lấy message2
         │                  │
         └── đợi completion trước khi write tiếp
```

Đây là *ý tưởng state machine*, không phải code mặc định thread-safe. Trong server đa thread cần lock/actor/event-loop để đảm bảo chỉ **một component** được quyền điều phối write và cập nhật `writePending`/queue. Nếu nhiều producer gọi thẳng `channel.write` đồng thời, bạn rất dễ gặp `WritePendingException` và còn khó bảo đảm thứ tự bytes trên TCP stream.

### 8.2. Tương tự cho read

Với đọc, một bộ phận quản lý connection giữ một **receive buffer** và state parser. Mỗi lần read hoàn tất: kiểm tra count, đưa các byte mới qua parser, quyết định cần đọc tiếp hay tạm dừng vì backpressure. Không cho nhiều thread độc lập bắt đầu read trên cùng socket “vì muốn tăng throughput”.

## 9. Số byte trả về không phải số byte của một message

TCP là **byte stream**, không bảo toàn ranh giới các lần `write` của ứng dụng. Khi peer gửi một chuỗi 10 KiB:

- Một lần `read` có thể chỉ nhận vài byte, vài KiB hoặc phần lớn dữ liệu.
- Hai lần `write` có thể được đọc chung trong một lần read.
- Một lần `write` có thể được nhận qua nhiều lần read.
- `read` thành công trả **n** bytes (n dương), không có nghĩa đã nhận một message ứng dụng đầy đủ.
- `-1` báo remote output đã đóng và toàn bộ data trước đó đã được nhận/tiêu thụ theo stream semantics.

Vì vậy ứng dụng phải có **framing**. Hai kiểu thường gặp:

1. **Length-prefix:** gửi 4 byte header ghi chiều dài N, rồi đúng N byte payload; reader đọc đủ header, validate N, đọc đủ body.
2. **Delimiter:** ví dụ mỗi message kết thúc bằng newline, nhưng phải quy định escape và giới hạn message size.

Không coi `read completed` là `protocol request completed`. Completion chỉ nói về **một I/O operation**.

### 9.1. Read 0 byte

Khi `dst.remaining() == 0` tại thời điểm đọc, async read có thể hoàn thành tức thì với kết quả `0` mà không làm I/O. Đây không phải EOF. Nếu buffer đầy mà parser chưa tiêu thụ, cần chuyển buffer về chế độ đọc, parse/compact và giải phóng dung lượng **sau completion**, không submit read vô hạn vào buffer không còn chỗ.

### 9.2. Write 0 byte

Tương tự, nếu `src.remaining() == 0`, write có thể hoàn tất ngay với 0. Đừng dùng một buffer ở position/limit sai rồi thắc mắc vì sao peer không nhận gì.

### 9.3. EOF và half-close

`AsynchronousSocketChannel.shutdownOutput()` đóng **chiều ghi** của socket mà không nhất thiết đóng toàn bộ kết nối. Peer có thể tiếp tục đọc dữ liệu đã gửi, rồi thấy EOF `-1`. Hai chiều đọc/ghi được tách, phù hợp TCP full-duplex. Không tự cho rằng EOF chiều đọc có nghĩa chiều ghi cũng phải đóng ngay; quy tắc đóng connection là một phần protocol của ứng dụng.

## 10. Các thao tác ByteBuffer: flip, clear, compact, slice, duplicate

### 10.1. Trước read: dành vùng trống

```java
ByteBuffer inbound = ByteBuffer.allocate(8192);
Future<Integer> f = socket.read(inbound);
```

Trong lúc `f` chưa hoàn thành, **không** gọi `inbound.position()`, `flip()`, `clear()`, `put()` hoặc decoder trên buffer đó. Sau khi kết quả read được xác nhận xong, có thể gọi:

```java
int n = f.get();
if (n > 0) {
    inbound.flip();
    // Decode hoặc parse phần dữ liệu đã nhận.
    inbound.compact();
}
```

Đây là snippet **trong phương thức**, có `Future<Integer> f` và xử lý checked exceptions. `compact()` chuyển phần chưa parse về đầu buffer và đặt lại vị trí để tiếp tục nhận dữ liệu. Nếu parser đã tiêu thụ toàn bộ, `clear()` có thể phù hợp hơn.

### 10.2. Trước write: nguồn phải ở chế độ đọc bytes

```java
ByteBuffer outbound = ByteBuffer.allocate(16);
outbound.put("hello".getBytes(StandardCharsets.UTF_8));
outbound.flip();
Future<Integer> sending = socket.write(outbound);
```

Không gọi `outbound.clear()` để “chuẩn bị message tiếp theo” khi `sending` còn pending. Provider có thể vẫn đang đọc bytes từ buffer. Sau khi Future đã hoàn thành, kiểm tra `outbound.hasRemaining()` để biết còn byte nào cần gửi tiếp.

### 10.3. duplicate() không phải bản sao độc lập

`ByteBuffer.duplicate()` và `slice()` tạo view với position/limit riêng, nhưng thường **chia sẻ cùng vùng nhớ nền**. Tạo duplicate của một buffer đang pending rồi ghi vào duplicate vẫn có thể thay đổi các bytes provider đang đọc/ghi:

```java
ByteBuffer view = outbound.duplicate();
view.put(0, (byte) 'X'); // SAI nếu outbound vẫn đang được async write dùng.
```

Đây là **anti-pattern**. `asReadOnlyBuffer()` ngăn sửa qua view cụ thể nhưng không đóng băng dữ liệu nền: owner vẫn có thể sửa qua buffer gốc hoặc một view khác.

Nếu nhiều thao tác cần dữ liệu độc lập, phải **copy bytes** sang buffer khác hoặc thiết lập ownership bất biến trong suốt thời gian async operation. Không xem `duplicate/slice` là một snapshot.

### 10.4. Heap và direct ByteBuffer

`ByteBuffer.allocate(n)` tạo heap buffer; `ByteBuffer.allocateDirect(n)` tạo direct buffer. Cả hai đều phải tuân thủ **giới hạn truy cập trong lúc pending**. Direct buffer không tự khiến một buffer an toàn để thay đổi từ nhiều thread và không xóa chi phí quản lý vòng đời.

Không nhất thiết dùng direct buffers cho mọi message: quyết định theo kích thước, tần suất, chi phí cấp phát/GC, provider và benchmark.

### 10.5. ByteBuffer thread safety và Java memory visibility

ByteBuffer chứa **trạng thái mutable** như position/limit. Async operation có thể cập nhật buffer trên thread khác. Khi caller nhận completion qua Future.get/handler, thời điểm này mới có cơ sở thao tác theo lifecycle của API.

Không dùng volatile flag tự phát để bỏ qua hợp đồng pending và đọc buffer trước completion. Khi handoff buffer từ callback cho worker khác, cần cơ chế đồng bộ như queue thread-safe, CompletableFuture, lock hoặc actor để đảm bảo quyền sở hữu chỉ chuyển sau khi read đã kết thúc.

## 11. CompletionHandler: giữ buffer riêng trong attachment/state

Dạng callback có timeout:

```java
socket.read(buffer, 5, TimeUnit.SECONDS, state,
        new CompletionHandler<Integer, SessionState>() {
    @Override
    public void completed(Integer n, SessionState session) {
        // Read đã hoàn thành: bây giờ mới được parse buffer.
        // Khi cần, submit read tiếp sau khi xử lý n và state.
    }

    @Override
    public void failed(Throwable error, SessionState session) {
        // Report, đóng/cancel session theo chính sách.
    }
});
```

Đây là **snippet trong phương thức**, `SessionState` là kiểu nghiệp vụ **giả định** chứa request/session/byte counters; không phải chương trình chạy độc lập. Callback được invoke theo async completion. Bạn có thể giữ buffer/state trong một object của session, nhưng không được có consumer khác đụng buffer trong lúc operation pending.

### 11.1. Tại sao chỉ submit read tiếp từ completed callback?

Nếu callback báo hoàn thành read với n bytes, operation cũ đã rời trạng thái pending. Lúc đó có thể:

1. Kiểm tra n, xử lý EOF khi -1.
2. Chuyển ByteBuffer sang chế độ đọc; parse phần đã nhận.
3. Xử lý framing và giữ bytes còn dở.
4. Quyết định có đủ capacity và cần đọc tiếp không.
5. Chuẩn bị buffer, rồi **submit read kế tiếp**.

Không submit read tiếp từ thread khác chỉ vì thấy một packet đã đến bằng cơ chế dự đoán timing. Cần một scheduler/state machine có concurrency control rõ.

### 11.2. CompletionHandler có thể được gọi trên thread khác

Thành công và thất bại được dispatch qua nhóm/thread pool gắn với asynchronous channel. Handler không có cam kết luôn chạy trên thread đã submit. Có trường hợp completion xảy ra rất nhanh và code chạy ở thread của pool, handler có thể được gọi trực tiếp. Vì vậy:

- Không cập nhật UI hoặc dữ liệu không thread-safe từ callback mà không dispatch.
- Không thực hiện blocking I/O dài trong completion handler làm nghẽn pool.
- Không giữ lock mà callback có thể phải lấy khi bạn submit operation nếu có khả năng re-entrancy.
- Không giả định hai callback của hai connections thực thi tuần tự.

### 11.3. Đối với write, callback phải giải phóng queue slot

Một write handler nhận n bytes. Nếu buffer còn remaining, handler **đưa tiếp cùng message còn thiếu**, sau khi hoàn thành write trước. Khi buffer hết, có thể lấy message tiếp theo từ outbound queue.

Nếu lỗi, handler phải báo request thất bại, dọn buffer/state và quyết định đóng connection/retry theo protocol. Không nuốt `failed` để giữ `writePending=true` mãi khiến connection không bao giờ gửi tiếp.

## 12. Future: hai loại timeout không giống nhau

### 12.1. Timeout của Future.get chỉ giới hạn thời gian chờ caller

```java
Future<Integer> pending = socket.read(dst);
try {
    int count = pending.get(3, TimeUnit.SECONDS);
} catch (TimeoutException waitExpired) {
    // Chỉ có nghĩa caller không nhận completion trong 3 giây.
    // read vẫn có thể đang pending.
}
```

Đây là snippet trong phương thức với `Future<Integer> pending`, `ByteBuffer dst`, imports TimeUnit/TimeoutException và xử lý `InterruptedException`, `ExecutionException`. `Future.get(timeout)` **không tự đặt timeout vào thao tác socket**. Nếu nó báo timeout, đừng giả định read slot đã trống hoặc buffer có thể tái sử dụng.

### 12.2. Timeout tham số của AsynchronousSocketChannel là timeout operation

API còn có:

```java
socket.read(dst, 3, TimeUnit.SECONDS, attachment, handler);
socket.write(src, 3, TimeUnit.SECONDS, attachment, handler);
```

Đây là chữ ký minh họa trong phương thức, với buffer/attachment/handler đúng loại. Nếu timeout của operation hết trước khi hoàn thành, operation được hoàn tất với `InterruptedByTimeoutException` qua handler failed. Đây là lỗi của **I/O operation** chứ không chỉ là caller dừng đợi Future.

**Điểm rất quan trọng trong Javadoc Java SE 17:**

- Sau timeout read/write, trạng thái của **ByteBuffer liên quan không được định nghĩa**.
- Nếu provider không chắc byte đã/đang được chuyển, channel có thể vào **implementation-specific error state**.
- Các read/write cùng loại tiếp theo có thể ném runtime exception không được chuẩn hóa.
- Giá trị timeout **≤ 0** của các overload có tham số timeout có nghĩa operation **không timeout**.

**Chính sách bảo thủ:** khi gặp operation timeout và integrity quan trọng, **không cố tái sử dụng buffer cũ trên channel còn mở**; cân nhắc đóng connection, bỏ buffer, khởi tạo session mới và xử lý retry ở mức protocol sau khi đã xác định idempotency. Không suy từ `position()` sau timeout rằng biết chính xác bytes nào đã tới peer.

### 12.3. Vì sao không thử nghiệm timeout bằng cách gọi read rồi đọc buffer?

Vì chính tài liệu API nói buffer state sau I/O timeout có thể không xác định. Một unit test đọc `buffer.position()` ngay khi failure xảy ra không chứng minh ứng dụng có thể tin giá trị đó trong mọi provider. Tốt hơn test rằng handler chuyển session sang trạng thái lỗi/closed và không dùng buffer cũ cho message kế tiếp.

## 13. Cancellation cũng cần chính sách quản lý buffer

`Future.cancel(...)` là yêu cầu hủy kết quả Future; nó không tương đương một transaction rollback của TCP. Có những trường hợp byte đã được ghi vào buffer hoặc chuyển tới socket trước khi cancellation được quan sát.

Không đặt mặc định:

```java
pending.cancel(true);
buffer.clear();  // Không an toàn nếu chưa chắc mọi I/O với buffer đã dừng.
```

Đây là **anti-pattern**. Với socket đã timeout/cancel, chính sách an toàn cho ứng dụng cần tính đúng có thể là **đóng connection và bỏ buffer** thay vì tiếp tục protocol trên một trạng thái không rõ. Với read/write muốn retry, ứng dụng phải phân biệt việc peer đã nhận/đã xử lý message hay chưa; TCP không cung cấp nghiệp vụ “exactly-once message delivery”.

### 13.1. Thế nào là “completion đã được quan sát”?

- Với Future, khi `get()` **trả thành công**, bạn có thể dùng buffer theo số byte thực nhận.
- Với CompletionHandler, trong `completed(...)` bạn có thể xử lý buffer của operation đã kết thúc.
- Với operation lỗi hoặc cancellation, việc tái sử dụng buffer cần xét **hợp đồng lỗi cụ thể**; timeout read/write có cảnh báo mạnh về undefined buffer state.
- Với shutdown chủ động, tốt hơn dừng nhận nhiệm vụ mới, hoàn tất/hủy có kiểm soát và đóng channel, không cho công việc tiếp tục giữ reference đến buffer đã trả về pool.

## 14. Trạng thái kết nối và operation pending không độc lập

### 14.1. Chưa connect thì không read/write được

Một `AsynchronousSocketChannel.open()` mới tạo còn chưa connected. Gọi `read/write` trước khi connected có thể ném `NotYetConnectedException`. Cần chờ kết quả của:

```java
Future<Void> connected = client.connect(remoteAddress);
connected.get(5, TimeUnit.SECONDS);
```

rồi mới gửi read/write. Khi connect đang pending, gọi connect lần hai có thể gặp `ConnectionPendingException`. Đừng dùng `getRemoteAddress()` trả một địa chỉ làm chứng minh mọi I/O trong tương lai sẽ thành công: peer có thể đóng hoặc mạng lỗi ngay sau đó.

### 14.2. shutdownInput, shutdownOutput và pending operations

`shutdownInput()` khiến các read mới trả EOF `-1`; tác động lên **read đang outstanding** là **system-dependent** theo Javadoc. `shutdownOutput()` chặn các write mới và có thể làm những write đang outstanding bị ảnh hưởng theo cách không được chuẩn hóa.

Đừng dùng shutdownInput/output như “hủy một operation chắc chắn không tác động buffer”. Khi cần kết thúc session, phải có logic state machine và thông báo lỗi/EOF cho tầng protocol.

### 14.3. Đóng socket trong lúc pending

`channel.close()` có thể khiến Future/handler của những thao tác pending hoàn tất với `AsynchronousCloseException` hoặc lỗi đóng liên quan. Mọi buffer/state của session cần được giải phóng theo vòng đời hợp lý; không giữ task đang chờ vô hạn.

Lỗi `ReadPendingException` khác với `ClosedChannelException` hoặc EOF. Một lỗi do **vi phạm mô hình concurrency của ứng dụng**, còn lỗi đóng/EOF thường là lifecycle/network condition.

## 15. Scattering read và gathering write cũng chịu giới hạn pending

Ngoài read/write với một ByteBuffer, `AsynchronousSocketChannel` có overload dùng **nhiều buffer**:

```java
socket.read(dstBuffers, offset, length,
        timeout, TimeUnit.SECONDS, state, readHandler);

socket.write(srcBuffers, offset, length,
        timeout, TimeUnit.SECONDS, state, writeHandler);
```

Đây là **snippet mô tả API**, với `ByteBuffer[] dstBuffers/srcBuffers`, `int offset/length`, `long timeout`, `state` và `CompletionHandler<Long,A>` tương ứng. Kết quả tổng số byte được chuyển qua callback kiểu **`Long`**, không phải `Integer` như overload single-buffer.

### 15.1. Không phải mỗi buffer có một pending slot

Scattering read của nhiều buffers **vẫn là một read operation đang pending** trên socket. Khi nó chưa hoàn thành, submit một read khác sẽ gặp `ReadPendingException`. Gather write tương tự đối với `WritePendingException`.

### 15.2. Không đụng bất kỳ buffer nào của operation đang pending

Với scattering/gathering, **tất cả những ByteBuffer tham gia operation** phải được giữ nguyên cho đến khi completion. Việc chỉ chạm một buffer ở phần sau mảng cũng có thể gây race. Hãy để một session/message frame sở hữu toàn bộ mảng cho tới khi handler callback hoàn thành.

### 15.3. Hạn chế của hệ điều hành

Javadoc ghi số buffer có thể chuyển trong một operation có thể chịu giới hạn OS; implementation có thể chỉ sử dụng số lượng buffers tối đa được phép trong lần I/O. Không coi một scattering read hay gathering write luôn điền/gửi hết mọi buffer trong mảng. Sau completion, kiểm tra `position/remaining` từng buffer rồi lên lịch phần còn thiếu.

## 16. Sự khác nhau giữa asynchronous socket và asynchronous file

Cùng mang chữ `Asynchronous` nhưng có những giới hạn khác:

| Đặc điểm | `AsynchronousSocketChannel` | `AsynchronousFileChannel` |
| --- | --- | --- |
| Loại dữ liệu | TCP byte stream | File theo offset |
| Outstanding operations | **Tối đa một read và một write** tại một thời điểm trên một socket | Có thể có nhiều reads/writes outstanding; phải quản lý buffers và overlapping regions |
| Position | Dựa trên thứ tự bytes stream TCP, không có explicit file offset | Mỗi read/write có `long position` |
| EOF | Peer shutdown output/đóng stream | Đọc tới/vượt EOF của file |
| Timeouts ở overload handler | Có read/write timeout và caveat buffer/channel mạnh | API read/write file cơ bản không có cùng overload timed socket |
| Buffer ownership | Không chạm tới completion | Không chạm tới completion |
| Thứ tự completion | Không coi callback là message boundary | Có thể hoàn tất không theo submit order |

**Không áp công thức “file cho nhiều outstanding reads ⇒ socket cũng cho nhiều reads”**. Socket giới hạn một read và một write; muốn song song nhiều logical requests trên một connection, ứng dụng cần **multiplex ở tầng protocol**, đọc tuần tự bytes và phân phối message theo ID sau khi parser xác định framing.

## 17. Điều phối đa thread: connection state machine

Một application có thể có:

- Thread thực hiện accept.
- Worker xử lý logic nghiệp vụ và enqueue outbound messages.
- Callback đọc vào buffer, parse message.
- Callback ghi tiêu thụ pending outbound queue.
- Timer cho connection idle/deadline.
- Thread shutdown hoặc cancellation.

Dù channel an toàn dùng từ nhiều thread, **trạng thái nghiệp vụ** quanh nó chưa chắc thread-safe. Một thiết kế gợi ý:

```text
ConnectionSession
    ├── socket: AsynchronousSocketChannel
    ├── readState
    │     ├── readPending: boolean
    │     ├── inboundBuffer: ByteBuffer
    │     └── protocolDecoder
    ├── writeState
    │     ├── writePending: boolean
    │     ├── queue<OutboundMessage>
    │     └── activeWriteBuffer
    └── lifecycle: CONNECTED / CLOSING / CLOSED
```

Chỉ **một owner/state machine** chuyển `readPending/writePending` từ false sang true và ngược lại. Nhiều producer chỉ **enqueue message**, không gọi channel.write trực tiếp. Callback truyền dữ liệu tới worker hoặc thực hiện một số bước state transition trong synchronized/actor context.

### 17.1. Đăng ký writePending phải atomic với submit

Nếu hai worker cùng thấy `writePending=false` rồi đều gọi `write`, một worker có thể gặp `WritePendingException` và queue bị lệch. Phải thiết kế transition an toàn (ví dụ lock hoặc serialized event loop):

1. Dưới lock chọn message và đánh dấu một write đang quản lý.
2. Thoát lock khi phù hợp rồi submit.
3. Nếu việc submit **ném ngoại lệ đồng bộ**, rollback/close state theo chính sách.
4. Khi callback hoàn thành, cập nhật số byte và quyết định submit phần còn lại/next message.
5. Khi đóng, cấm submit mới và fail những message chưa gửi.

**Không dùng duy nhất `volatile boolean writePending`** với check-then-act không atomic nếu nhiều thread có thể cùng submit.

### 17.2. Có nên reset pending flag trước khi parse nặng?

Đừng đánh dấu read slot “rảnh để component khác submit” khi buffer còn chưa được parser xử lý nếu việc đó có thể khiến receive buffer bị tái sử dụng sai. Tách khái niệm **I/O operation completed** và **buffer/session đã được bàn giao an toàn**.

### 17.3. Backpressure

Một reader có thể nhận dữ liệu nhanh hơn business worker xử lý. Một writer có thể enqueue message nhanh hơn network gửi đi. Cần **giới hạn bytes trong queue**, số message, số connection, timer và chính sách khi queue đầy. Nếu không, ứng dụng có thể gây OOM dù mỗi socket chỉ có một read/one write pending.

Ví dụ áp dụng bounded outbound queue; khi full, từ chối request mới hoặc báo backpressure theo giao thức, không tiếp tục allocate buffers vô hạn.

## 18. ByteBuffer pool: tối ưu hóa nhưng dễ trả buffer quá sớm

Giả sử bạn dùng pool có 100 `ByteBuffer` để giảm allocations. Một lỗi rất nguy hiểm là:

```java
ByteBuffer buf = pool.borrow();
Future<Integer> sending = socket.write(buf);
pool.release(buf); // SAI: write có thể vẫn đang dùng buf.
```

Đây là **anti-pattern minh họa**, `pool` là API giả định của ứng dụng. Phần bytes ở buffer có thể bị request khác ghi đè trong lúc provider đang gửi message cũ.

**Đúng về lifetime:** chỉ trả buffer về pool khi operation cuối cùng dùng buffer đã kết thúc và không còn callback/worker giữ reference để đọc bytes chưa được xử lý. Với read, chỉ trả sau khi parser đã đọc/copy dữ liệu cần thiết. Với write, chỉ trả sau khi toàn message đã gửi hết hoặc sau khi lỗi được xử lý an toàn.

### 18.1. Không dùng duplicate/slice thay cho quyền sở hữu

`duplicate()` và `slice()` có views nhưng **chia sẻ backing memory**. Dù mỗi view có position riêng, ghi vào memory qua một view vẫn ảnh hưởng dữ liệu operation của view khác. Nếu cần immutable outbound payload khi nhiều producer sửa dữ liệu, tạo bản sao độc lập và giữ ownership qua completion.

### 18.2. Dọn sau timeout

Với API socket read/write timed, sau `InterruptedByTimeoutException` trạng thái buffer không được định nghĩa theo Javadoc. Trong hệ thống ưu tiên tính đúng, không đưa buffer đó vào pool để một session khác sử dụng khi channel cũ còn mở và tình trạng I/O chưa rõ. Cân nhắc đóng connection, bỏ buffer và chuyển session sang trạng thái lỗi.

## 19. Các lỗi và cách xử lý đúng

| Trường hợp | Tín hiệu/exception | Ý nghĩa thực tế |
| --- | --- | --- |
| Read thứ hai trước khi read đầu xong | `ReadPendingException` | Logic application đang vi phạm 1 outstanding read |
| Write thứ hai trước khi write đầu xong | `WritePendingException` | Cần queue/serialize writes |
| Accept thứ hai trên listener còn accept pending | `AcceptPendingException` | Cần wait/completion rồi accept tiếp |
| Connect thứ hai khi connect đầu pending | `ConnectionPendingException` | Quản lý lifecycle connect |
| Read/write trên socket chưa kết nối | `NotYetConnectedException` | Chờ connect completion |
| `Future.get(timeout)` hết thời gian | `TimeoutException` | Caller đợi quá lâu; I/O có thể còn pending |
| Async read/write timed overload hết thời gian | `InterruptedByTimeoutException` | I/O timeout, buffer state có thể undefined |
| Future completion thất bại | `ExecutionException` | Lỗi thật trong cause |
| Thread chờ bị interrupt | `InterruptedException` | Xử lý interrupt policy |
| Callback lỗi | `failed(Throwable,A)` | Báo business failure và release session |
| Channel bị đóng trong lúc pending | `AsynchronousCloseException`/lỗi đóng tương ứng | Không dùng connection như còn sống |
| Peer đóng output | Read trả `-1` | EOF, không phải ReadPendingException |
| Read có buffer read-only | `IllegalArgumentException` | Destination cần writable |
| Scattering/gathering offset/length không hợp lệ | `IndexOutOfBoundsException` | Validate slice trong mảng |
| Async channel group đã terminated | `ShutdownChannelGroupException` | Không được mở/submit theo group đã shutdown |

Không bắt toàn bộ `IllegalStateException` rồi retry mù quáng, vì `ReadPendingException`, `WritePendingException` và các lỗi trạng thái khác có thể cùng kế thừa loại unchecked nhưng có nguyên nhân khác. Trong code production, ghi log với connection/request ID và có chính sách rõ cho từng lỗi.

## 20. Giám sát, kiểm thử và tính portable

### 20.1. Điều có thể kiểm thử từ hợp đồng API

- Trên một accepted socket chưa nhận dữ liệu, bắt đầu read rồi cố read thêm ⇒ `ReadPendingException`.
- Trên listener chưa có incoming connection, bắt đầu accept rồi thử accept nữa ⇒ `AcceptPendingException`.
- Trong khi một read pending, một write cùng socket được phép.
- Sau successful completion, `ByteBuffer.position()` tăng theo số bytes đã chuyển.
- Read trả EOF `-1` khi peer shutdown output và bytes đã tiêu thụ hết.
- Buffer không được bị caller thay đổi trước completion.

### 20.2. Điều không nên assert tuyệt đối

- Viết 4 byte trên TCP sẽ tạo một read duy nhất nhận đúng 4 byte.
- Write thứ nhất luôn pending đủ lâu để gây `WritePendingException` ở write thứ hai.
- Callback luôn được chạy trên thread cụ thể.
- Future.get sẽ hoàn thành trong 10 ms trên mọi máy.
- Mọi provider/OS có cùng timeout/cancel semantics cấp kernel.
- Nếu write Future hoàn thành thì remote application đã parse và commit message.

### 20.3. Testing chiến lược

Test protocol framing và send queue bằng **unit tests** độc lập với network timing. Dùng integration test trên loopback để kiểm tra Future/callback, full-duplex, pending exceptions và EOF. Test stress/slow peer riêng có giới hạn memory/time, không ép giữ hàng nghìn megabyte để làm queue đầy.

Metrics hữu ích gồm:

- Số active connections.
- Số operation pending read/write (theo state machine).
- Độ dài/bytes của outbound queue.
- Read/write completion latency, timeout/error count.
- Số partial transfers và số message còn chờ framing.
- Buffer pool available/in-use, bytes đang in-flight.
- Số callbacks/worker queue bị chậm hoặc nghẽn.

**Không đo pending bằng việc đọc `ByteBuffer.position()` liên tục từ thread khác trong lúc I/O chạy.** Hãy cập nhật metrics từ state machine và callbacks đã đồng bộ.

## 21. Những lỗi dễ mắc nhất

**1. “AsynchronousSocketChannel có thể có nhiều read cùng lúc vì thread-safe.”** Sai. Thread-safe access không thay đổi giới hạn **một outstanding read**.

**2. “Chỉ được một operation tổng cộng nên không thể read và write đồng thời.”** Sai. **Một read và một write** được phép cùng pending.

**3. “Hai ByteBuffer khác nhau có thể giúp thực hiện hai read pending trên cùng socket.”** Sai. ReadPendingException theo **socket operation slot**, không theo buffer identity.

**4. “Ghi hai message nhỏ liên tiếp luôn gây WritePendingException.”** Sai; write đầu có thể hoàn thành ngay.

**5. “Future.read đã trả về thì buffer được dùng thoải mái.”** Sai; Future trả về chỉ cho biết operation đã được khởi tạo.

**6. “Đọc `position()` của buffer pending là vô hại.”** Không có bảo đảm an toàn khi provider đang cập nhật buffer.

**7. “Có thể gọi `clear()` và tái sử dụng buffer sau khi submit write.”** Sai; có thể ghi đè message chưa gửi.

**8. “duplicate() tạo bản sao bytes độc lập.”** Sai; thường chia sẻ backing storage.

**9. “Sau read completed, buffer tự flip.”** Không; ứng dụng cần flip để parse bytes.

**10. “Một read completion luôn chứa đủ logical message.”** Sai; TCP là byte stream, cần framing.

**11. “Write completion nghĩa là peer application đã xử lý dữ liệu.”** Sai; không phải business ACK.

**12. “read() trả 0 nghĩa là EOF.”** Sai. Nếu destination không còn remaining thì async read có thể hoàn tất 0; EOF là -1.

**13. “Future.get(timeout) hủy I/O khi timeout.”** Sai. Nó chỉ giới hạn thời gian chờ.

**14. “Timed read failure vẫn có thể tin buffer.position.”** Sai; Javadoc cảnh báo buffer state undefined sau timeout.

**15. “Timeout operation xong nghĩa là channel chắc chắn dùng bình thường tiếp được.”** Không; có thể vào provider-specific error state.

**16. “Cancel Future cho phép trả ByteBuffer về pool ngay.”** Không nên, nếu chưa xác định được trạng thái outstanding I/O.

**17. “Callback chắc chắn chạy trên caller thread.”** Sai; liên quan async group/thread pool.

**18. “CompletionHandler.completed được gọi sau khi mọi protocol message bytes đã tới đủ.”** Sai; chỉ xong **một read/write operation**.

**19. “Hai concurrent writes sẽ giữ thứ tự message.”** Socket không cho phép hai writes pending; cần **serialize writes** từ queue.

**20. “Scattering read cho phép mỗi buffer một read pending.”** Sai; cả mảng là **một operation**.

**21. “Một listener có thể có nhiều accept pending chỉ vì nhiều clients.”** Không; một accept pending trên mỗi AsynchronousServerSocketChannel.

**22. “EOF chắc chắn có nghĩa application phải đóng cả hai chiều tức thì.”** Không; half-close có semantics riêng, tùy protocol.

**23. “AsynchronousFileChannel có nhiều pending reads nên socket cũng có.”** Sai; API contracts khác nhau.

**24. “Chỉ cần volatile boolean cho queue nhiều producers.”** Không đủ với check-then-submit không atomic.

**25. “Thread pool lớn là đủ tránh backpressure.”** Không. Cần giới hạn bytes in-flight và số messages.

**26. “Nếu TCP write Future xong thì có thể retry cùng message không cần ID.”** Không; retry cấp protocol cần idempotency/ACK để tránh trùng.

## 22. Checklist khi review AsynchronousSocketChannel

- [ ] Một socket có tối đa **một read và một write pending** theo state machine?
- [ ] Đã phân biệt `ReadPendingException` với `WritePendingException`?
- [ ] Nhiều producer không gọi `write` đồng thời trên cùng socket mà qua queue?
- [ ] Có bảo đảm transition `writePending/readPending` an toàn giữa threads?
- [ ] Sau accept completion, listener mới bắt đầu accept tiếp khi còn cần?
- [ ] Không bắt đầu read/write trước connect completion?
- [ ] Không chạm `ByteBuffer` từ caller cho đến Future success/handler completion?
- [ ] Không `clear/flip/put/get/position` trên buffer của operation còn pending?
- [ ] Có đảm bảo ByteBuffer pool không tái cấp buffer khi nó vẫn đang dùng?
- [ ] Có biết `duplicate/slice` chia sẻ backing memory?
- [ ] Có dùng `flip/compact/clear` đúng trạng thái, sau completion?
- [ ] Có xử lý partial read/write bằng count và `hasRemaining()`?
- [ ] Có framing TCP messages thay vì coi một read bằng một message?
- [ ] Có xử lý `-1` EOF và half-close riêng với 0 byte?
- [ ] Có giới hạn message size, outbound queue bytes và số operations in-flight?
- [ ] Có phân biệt `Future.get(timeout)` với timed async read/write?
- [ ] Sau `InterruptedByTimeoutException` có bỏ buffer/cân nhắc đóng channel thay vì đọc trạng thái undefined?
- [ ] Có xử lý `ExecutionException`, `InterruptedException`, `failed` callback?
- [ ] Nếu cancel, đã xác lập buffer/resource lifetime rõ?
- [ ] Callback có ngắn gọn, không block completion thread pool quá lâu?
- [ ] Có bảo đảm send queue giữ đúng thứ tự và không drop partial writes?
- [ ] Có xử lý connection/group shutdown và pending operation failures?
- [ ] Integration tests có kiểm tra ReadPending, AcceptPending, full-duplex và EOF?
- [ ] Không viết test bắt buộc WritePendingException khi gửi message nhỏ trên loopback?
- [ ] Metrics không truy cập buffer mutable đang pending từ thread khác?
- [ ] Cơ chế retry có protocol ID/ACK/idempotency khi cần tính đúng?
- [ ] Bản demo chạy Java 17+ mà không cần lớp internal/legacy?

## 23. Câu hỏi tự kiểm tra

**1.** Pending I/O là gì? — Một operation đã bắt đầu nhưng chưa completed/failed.

**2.** Một AsynchronousSocketChannel cho bao nhiêu read pending? — **Một**.

**3.** Một AsynchronousSocketChannel cho bao nhiêu write pending? — **Một**.

**4.** Một read và một write trên cùng socket có thể cùng pending? — **Có**, hỗ trợ full-duplex.

**5.** Lệnh read thứ hai khi read đầu chưa xong gây gì? — `ReadPendingException`.

**6.** Lệnh write thứ hai khi write đầu chưa xong gây gì? — `WritePendingException`.

**7.** Có chắc hai write nhỏ liên tiếp sẽ gây WritePendingException? — **Không**, write trước có thể đã completed.

**8.** Một listener có thể có hai accept pending đồng thời không? — **Không**, `AcceptPendingException`.

**9.** Nếu hai reads dùng hai buffer khác nhau trên cùng socket thì sao? — Vẫn vi phạm một pending read.

**10.** Có được gọi `buffer.flip()` khi async read vẫn pending? — **Không**.

**11.** Khi nào có thể đọc buffer sau async read? — **Sau khi** operation hoàn thành và kết quả được nhận.

**12.** `Future.get()` có thể chặn không? — **Có**.

**13.** `Future.get(timeout)` timeout có tự động hủy read? — **Không**.

**14.** Timed asynchronous read hết timeout trả lỗi gì? — `InterruptedByTimeoutException` qua failed callback.

**15.** Sau timed read timeout có tin giá trị buffer.position không? — **Không**, trạng thái buffer có thể undefined.

**16.** Channel có thể trở thành error state sau timeout không? — **Có**, tùy provider.

**17.** `duplicate()` có làm dữ liệu buffer thành bản sao độc lập không? — **Không**, chia sẻ backing bytes.

**18.** Một read có thể nhận ít hơn số byte đợi không? — **Có**, TCP không giữ message boundaries.

**19.** `read() == -1` có nghĩa gì? — EOF từ stream/peer output.

**20.** Buffer remaining 0 và read trả 0 có phải EOF không? — **Không**.

**21.** Một write completion có nghĩa peer đã xử lý business message không? — **Không**, cần ACK cấp protocol khi cần.

**22.** Callback có nhất thiết chạy trên caller thread không? — **Không**.

**23.** Scattering read với ba buffers có tạo ba read pending không? — **Không**, một read operation.

**24.** Scattering/gathering callback trả số byte kiểu nào? — `Long`.

**25.** Vì sao cần outbound queue? — Serialize writes, giữ partial bytes và chống WritePendingException.

**26.** Vì sao cần buffer pool ownership? — Tránh gửi dữ liệu bị request khác ghi đè khi write pending.

**27.** Vì sao không dùng một boolean thường cho nhiều thread submit? — Có race giữa check và submit, cần serialization/atomicity.

**28.** Tại sao có thể nhận `ReadPendingException` nhưng cùng lúc vẫn gửi `pong`? — Read và write slots độc lập.

**29.** Mô hình file async có cùng giới hạn socket không? — Không; `AsynchronousFileChannel` có contract khác và cho phép nhiều outstanding I/O.

**30.** Khi ưu tiên tính đúng sau timeout không rõ dữ liệu, giải pháp thường là gì? — Đóng connection, bỏ buffer không rõ trạng thái và khôi phục theo giao thức có idempotency.

## Tài liệu chính thức còn áp dụng

- [Java SE 17 — AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): một outstanding read + một outstanding write, timeout semantics, EOF và overloads Future/CompletionHandler.
- [Java SE 17 — AsynchronousByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousByteChannel.html): buffer ownership trong pending I/O, position/limit, read/write count.
- [Java SE 17 — AsynchronousServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): accept lifecycle và AcceptPendingException.
- [Java SE 17 — ReadPendingException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ReadPendingException.html): read thứ hai khi read trước chưa completed.
- [Java SE 17 — WritePendingException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/WritePendingException.html): write thứ hai khi write trước chưa completed.
- [Java SE 17 — AcceptPendingException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AcceptPendingException.html): accept thứ hai trên listener khi accept trước pending.
- [Java SE 17 — InterruptedByTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/InterruptedByTimeoutException.html): I/O operation timed out.
- [Java SE 17 — CompletionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): completed/failed, attachment.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): position/limit/flip/compact/duplicate/slice.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): get/cancel/isDone và timeouts.
- [Java SE 17 — AsynchronousChannelGroup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html): group, thread pool và shutdown lifecycle.

**Ghi nhớ:** `AsynchronousSocketChannel` cho **một read đang chờ và một write đang chờ**, hai chiều được phép chạy song song. Read thứ hai khi read trước chưa kết thúc gây `ReadPendingException`; write thứ hai tương tự gây `WritePendingException`. `ByteBuffer` của operation **không được caller truy cập hay tái sử dụng trước completion**; sau completion phải dùng count/position và xử lý partial bytes đúng cách. Đặc biệt, **timeout của Future.get khác timeout của async read/write**, và timed I/O có thể để buffer ở trạng thái không xác định. Khi server có nhiều producers, hãy điều phối qua state machine/queues, quản lý buffer ownership và xử lý lỗi/lifecycle rõ ràng.