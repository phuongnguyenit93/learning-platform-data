# Giới hạn số thao tác đồng thời và áp lực lên tài nguyên trong Java NIO I/O bất đồng bộ

## 1. Vì sao async I/O vẫn cần giới hạn?

I/O bất đồng bộ (asynchronous I/O) trong `java.nio.channels` cho phép khởi tạo thao tác đọc/ghi rồi nhận kết quả sau thông qua `Future` hoặc `CompletionHandler`. Luồng gửi yêu cầu không nhất thiết phải đợi thao tác I/O hoàn thành.

Tuy nhiên, **không chặn luồng gọi không có nghĩa thao tác miễn phí tài nguyên**. Nếu ứng dụng liên tục phát động yêu cầu mới mà không kiểm soát tốc độ, hệ thống có thể phải giữ rất nhiều buffer, callback, socket, file descriptor, dữ liệu đang chờ xử lý và công việc trong queue. Khi quá tải, độ trễ tăng, bộ nhớ cạn, lỗi timeout xuất hiện và cả những request bình thường cũng bị ảnh hưởng.

Ví dụ: 10.000 thao tác đọc, mỗi thao tác sở hữu `ByteBuffer` 1 MiB, tạo ra **xấp xỉ 10.000 MiB (gần 9,8 GiB)** dung lượng vùng byte ở mức lý thuyết, chưa tính object, queue, native memory, cache và các tài nguyên khác. Việc dùng `AsynchronousFileChannel` không tự giải quyết bài toán này.

Bài học thuộc **Java Core I/O → I/O bất đồng bộ**. Trọng tâm là xác định chính xác “đồng thời” đang đo cái gì, giới hạn in-flight operations, chọn executor/channel group, backpressure, quyền sở hữu `ByteBuffer`, xử lý hoàn thành/thất bại, đóng tài nguyên và vận hành an toàn.

## 2. Ba con số không được đánh đồng

Các hệ thống async thường có nhiều mức giới hạn riêng:

| Chỉ số | Định nghĩa | Hậu quả nếu quá lớn |
| --- | --- | --- |
| **In-flight operations** | Số I/O đã phát động nhưng chưa hoàn tất | Giữ buffer, kernel resources, callbacks; có thể cạn tài nguyên |
| **Worker/completion threads** | Số luồng dùng để thực thi hoặc phát callback | Context switching/CPU và nguy cơ callback chiếm hết luồng |
| **Queued work / pending bytes** | Số request hoặc số byte đang xếp hàng, chưa được phát I/O hoặc chưa gửi hết | Tích lũy bộ nhớ, tăng latency, mất kiểm soát áp lực |

Ví dụ `ExecutorService` có 4 thread **không tự chứng minh** chỉ có 4 I/O đang chờ. Một thread có thể khởi tạo nhiều thao tác async và trả về ngay; khi đó số thao tác đang chờ có thể cao hơn nhiều so với số worker. Ngược lại, giới hạn `in-flight=4` không có nghĩa chương trình luôn có đúng 4 thread vật lý hoặc chạy nhanh gấp 4 lần.

Nên đo riêng `activeIo`, `pendingRequests`, `pendingBytes`, `callbackDuration`, `requestLatency`, số open channels, lỗi/timeout và tỷ lệ từ chối.

## 3. Những API Java NIO liên quan

### `AsynchronousFileChannel`

`AsynchronousFileChannel.open(path, options, executor, attrs...)` mở file channel có thể đọc/ghi theo vị trí tuyệt đối `long`. `read(dst, position, attachment, handler)` khởi tạo một thao tác rồi callback được gọi với số byte đã đọc hoặc ngoại lệ. Một channel có thể có **nhiều thao tác đọc/ghi đồng thời**, nhưng thứ tự hoàn thành **không được bảo đảm giống thứ tự phát động**.

Tùy provider, async file I/O có thể được triển khai thông qua luồng trong executor chứ không nhất thiết bằng một giao diện kernel asynchronous thuần túy. Số luồng executor và số thao tác đã gửi vẫn là hai giới hạn khác nhau.

### `AsynchronousSocketChannel`

`AsynchronousSocketChannel` cho phép **tối đa một thao tác read đang chờ và một thao tác write đang chờ trên cùng channel tại một thời điểm**. Một read và một write có thể đồng thời tồn tại, nhưng gọi read thứ hai trước khi read trước hoàn tất sẽ ném `ReadPendingException`; tương tự write gây `WritePendingException`.

Điều này chỉ là giới hạn **trên mỗi socket**, không phải giới hạn toàn dịch vụ: 20.000 socket có thể đồng thời có tới 20.000 read pending, và còn các write cùng tồn tại. Cần cả chính sách quota trên connection và toàn ứng dụng.

### `AsynchronousChannelGroup`

Các asynchronous socket/server channels có thể gắn với một `AsynchronousChannelGroup`, liên kết với thread pool dùng để điều phối completion. Quản lý group giúp ứng dụng điều khiển lifecycle và tài nguyên phục vụ nhiều channel.

Đừng đồng nhất `AsynchronousChannelGroup` với `AsynchronousFileChannel.open(..., ExecutorService)`: file channel có thể nhận executor trực tiếp; socket channels dùng channel group. Cũng không mặc định rằng cấu hình `fixedThreadPool(8)` sẽ tự tạo một **bounded application request queue**.

### `Future` và `CompletionHandler`

Với `Future<Integer>`, lời gọi `future.get()` trong luồng phát động sẽ **chặn chính luồng đó** cho đến khi hoàn thành. Với `CompletionHandler`, luồng khởi tạo thường không phải chờ `get`, nhưng callback vẫn phải chạy trên một luồng và vẫn tiêu tốn CPU. Nếu callback chứa logic chặn lâu, đọc database đồng bộ hoặc xử lý CPU nặng, throughput có thể giảm mạnh.

## 4. Vòng đời một thao tác async và lúc giữ tài nguyên

```text
Yêu cầu đến
     |
     v
Kiểm tra quota + lấy permit + cấp buffer
     |
     v
Phát động I/O async (IN-FLIGHT)
     |
     +---- hoàn thành thành công --> xử lý kết quả / chuyển sang phase tiếp
     |
     +---- thất bại / timeout --> xử lý lỗi / đóng hoặc retry theo policy
     |
     v
Giải phóng permit và buffer khi thao tác thực sự kết thúc
     |
     v
Nhận yêu cầu tiếp theo từ hàng đợi có giới hạn
```

**Permit** là “quyền” cho phép giữ một slot I/O đang chạy. Nếu giới hạn 32, số thao tác được theo dõi bởi limiter không vượt 32. Cần giữ permit **suốt vòng đời** của một yêu cầu nếu yêu cầu ấy còn phát sinh nhiều lượt đọc lại để hoàn tất payload; chỉ trả permit khi hoạt động logic được coi là xong hoặc đã xử lý hủy theo hợp đồng của provider.

Đặt `release()` quá sớm ngay sau lời gọi `channel.read(...)` là sai: lời gọi chỉ **khởi tạo** async read, còn buffer và channel có thể đang được sử dụng. Cấp lại permit lúc ấy cho phép các yêu cầu mới tràn vào dù yêu cầu trước chưa hoàn tất.

## 5. Tính ngân sách bộ nhớ trước khi chọn giới hạn

Nếu một request giữ một buffer tối đa `B` byte và tối đa `N` thao tác in-flight, phần bộ nhớ cho các buffer vào khoảng:

```text
memoryForBuffers ≈ N × B

Tổng ngân sách ≈ memoryForBuffers
               + pending application payloads
               + outbound queues
               + connection state
               + executor queue / task objects
               + runtime, TLS, native, file-system resources
```

Ví dụ:

| Max in-flight | Buffer/request | Tổng dung lượng vùng byte, chưa tính overhead |
| ---: | ---: | ---: |
| 16 | 64 KiB | 1 MiB |
| 128 | 64 KiB | 8 MiB |
| 512 | 256 KiB | 128 MiB |
| 10.000 | 1 MiB | ≈ 9,77 GiB |

`ByteBuffer.allocate()` thông thường sử dụng heap; `ByteBuffer.allocateDirect()` sử dụng direct/native memory với các giới hạn và đặc điểm GC khác. **Direct buffer không đồng nghĩa không chiếm RAM.** Số lượng direct buffer lớn có thể gây `OutOfMemoryError: Direct buffer memory` hoặc áp lực native memory ngay cả khi heap còn chỗ.

Nếu ứng dụng giữ buffer trong một object pool, bộ nhớ có thể vẫn được giữ sau khi I/O kết thúc. Pool giảm chi phí cấp phát lặp lại, nhưng pool **không giới hạn** hoặc buffer quá cỡ có thể làm tình hình tệ hơn.

Ngân sách còn phụ thuộc loại buffer, độ dài thông điệp, số kết nối, số byte outbound chưa gửi và tốc độ người dùng xử lý kết quả. Quota theo **số tác vụ** thường cần phối hợp với quota theo **số byte**.

## 6. Dùng `Semaphore` để giới hạn I/O đang bay

`java.util.concurrent.Semaphore` là cách trực tiếp để biểu diễn số slot còn lại:

```java
Semaphore permits = new Semaphore(32);

// Ở vị trí nhận request có thể chờ:
permits.acquire();
try {
    // Cấp tài nguyên và bắt đầu async operation.
    // Sau khi phát động, KHÔNG release ngay tại đây.
} catch (RuntimeException e) {
    // Nếu chưa có completion callback nào sẽ nhận trách nhiệm cleanup,
    // giải phóng permit đã lấy.
    permits.release();
    throw e;
}

// CompletionHandler ở nhánh kết thúc:
try {
    // xử lý success hoặc failed
} finally {
    permits.release();
}
```

Đây là **các đoạn minh họa đặt trong nhiều vị trí**, không phải một hàm Java chạy độc lập. Ở production phải tổ chức trạng thái để bảo đảm **mỗi permit trả đúng một lần**, kể cả callback thất bại, khởi tạo thất bại, cancellation và shutdown. Nếu một thao tác có thể callback thành công/thất bại ngay tại luồng khởi tạo, tránh các race giữa nhánh submit và callback.

Dùng `tryAcquire()` để không chặn thread điều phối khi hết slot:

```java
if (!permits.tryAcquire()) {
    // Từ chối, trả tín hiệu "busy" hoặc xếp vào bounded queue.
    // Không âm thầm tích lũy hàng triệu request.
    return;
}
```

Trong một event loop, tránh `Semaphore.acquire()` vì **chặn thread xử lý sự kiện**; dùng `tryAcquire()`, hàng đợi giới hạn hoặc cơ chế cấp quota bất đồng bộ. Trong batch job có luồng producer riêng, `acquire()` có thể là backpressure đơn giản và hợp lệ.

### 6.1. Chọn chính sách khi hết permit

- **Wait**: producer chờ, thích hợp với batch job hoặc luồng ngoài event loop.
- **Bounded queue**: chờ có thứ tự tới một giới hạn rõ ràng; queue đầy thì từ chối hoặc chờ ở tầng ngoài.
- **Fail fast**: trả lỗi bận, ví dụ HTTP 429/503 (nếu ứng dụng là server phù hợp).
- **Load shedding**: bỏ yêu cầu ưu tiên thấp hoặc kết nối đang quá chậm theo policy rõ ràng.
- **Adaptive limit**: thay đổi số slot dựa trên latency, CPU, bộ nhớ và sai số đo, cần đo kiểm để tránh dao động.

Không dùng `Executors.newFixedThreadPool(k)` như một “giải pháp quota tổng quát” mà quên rằng `newFixedThreadPool` mặc định đi kèm **hàng đợi không giới hạn** cho các tác vụ đã nộp vào pool.

## 7. Ví dụ Java 17+ chạy được: đọc file async với tối đa hai job đồng thời

Chương trình dùng `AsynchronousFileChannel`, `CompletionHandler`, `Semaphore(2)`, `CountDownLatch` và một executor hai luồng. File tạm chứa `ABCDEFGHIJKL` được chia thành ba vùng 4 byte; mọi vùng được đọc bất đồng bộ, nhưng **tối đa hai job logic in-flight**.

Chương trình **không giả định thứ tự callback**: mỗi job lưu kết quả vào vị trí riêng, chỉ in kết quả sau khi tất cả hoàn tất. Nếu một lần đọc trả ít hơn 4 byte, cùng job tiếp tục đọc phần còn thiếu ở offset tiếp theo trong khi giữ permit.

Tạo file `AsyncIoLimitDemo.java`:

```java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;

public class AsyncIoLimitDemo {
    private static final int BLOCK_SIZE = 4;
    private static final int MAX_IN_FLIGHT = 2;

    private static class ReadJob implements CompletionHandler<Integer, Void> {
        private final AsynchronousFileChannel channel;
        private final ByteBuffer buffer = ByteBuffer.allocate(BLOCK_SIZE);
        private final long fileOffset;
        private final int index;
        private final String[] results;
        private final Throwable[] errors;
        private final Semaphore permits;
        private final CountDownLatch done;
        private final AtomicBoolean settled = new AtomicBoolean();

        ReadJob(AsynchronousFileChannel channel, long fileOffset, int index,
                String[] results, Throwable[] errors,
                Semaphore permits, CountDownLatch done) {
            this.channel = channel;
            this.fileOffset = fileOffset;
            this.index = index;
            this.results = results;
            this.errors = errors;
            this.permits = permits;
            this.done = done;
        }

        void submit() {
            try {
                long nextPosition = fileOffset + buffer.position();
                channel.read(buffer, nextPosition, null, this);
            } catch (RuntimeException ex) {
                finish(null, ex);
            }
        }

        @Override
        public void completed(Integer n, Void ignored) {
            if (n == null || n < 0) {
                finish(null, new EOFException("Unexpected EOF"));
                return;
            }
            if (n == 0) {
                // Đoạn demo chọn báo lỗi để tránh vòng lặp retry liên tục.
                finish(null, new IOException("Read made no progress"));
                return;
            }
            if (buffer.hasRemaining()) {
                submit(); // Vẫn giữ cùng permit cho tới khi đủ BLOCK_SIZE.
                return;
            }

            buffer.flip();
            byte[] bytes = new byte[buffer.remaining()];
            buffer.get(bytes);
            finish(new String(bytes, StandardCharsets.US_ASCII), null);
        }

        @Override
        public void failed(Throwable error, Void ignored) {
            finish(null, error);
        }

        private void finish(String value, Throwable error) {
            if (!settled.compareAndSet(false, true)) {
                return; // bảo vệ cleanup nếu ứng dụng gọi finish lặp lại
            }
            results[index] = value;
            errors[index] = error;
            permits.release(); // Một permit cho mỗi job logic.
            done.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("async-io-limits-", ".dat");
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Files.writeString(
                    file, "ABCDEFGHIJKL", StandardCharsets.US_ASCII);

            try (AsynchronousFileChannel channel =
                    AsynchronousFileChannel.open(
                            file, Set.of(StandardOpenOption.READ), pool)) {

                Semaphore permits = new Semaphore(MAX_IN_FLIGHT);
                CountDownLatch done = new CountDownLatch(3);
                String[] results = new String[3];
                Throwable[] errors = new Throwable[3];

                for (int i = 0; i < 3; i++) {
                    // Đây là batch producer ở main, không phải event loop.
                    permits.acquire();
                    new ReadJob(channel, i * (long) BLOCK_SIZE, i,
                            results, errors, permits, done).submit();
                }

                done.await();
                for (int i = 0; i < results.length; i++) {
                    if (errors[i] != null) {
                        throw new IOException("Job " + i + " failed", errors[i]);
                    }
                    System.out.println("chunk " + i + ": " + results[i]);
                }
                System.out.println("in-flight limit: " + MAX_IN_FLIGHT);
            }
        } finally {
            pool.shutdown();
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac AsyncIoLimitDemo.java
java AsyncIoLimitDemo
```

Stdout khi file tạm tạo thành công và hệ thống tệp hoạt động bình thường:

```text
chunk 0: ABCD
chunk 1: EFGH
chunk 2: IJKL
in-flight limit: 2
```

**Tại sao stdout ổn định?** Các completion callback có thể đến theo bất kỳ thứ tự nào, nhưng chúng ghi vào `results[index]`; luồng main đợi `done.await()` rồi mới in theo index. `CountDownLatch` cũng thiết lập quan hệ happens-before cho cập nhật trước `countDown()`. Chương trình không in thứ tự callback hoặc một “số thao tác đỉnh” có thể thay đổi tùy lịch trình.

**Giải thích giới hạn:**

1. `MAX_IN_FLIGHT=2` tạo hai permit. Job 0 và 1 có thể bắt đầu; producer chỉ phát động job 2 khi một completion đã trả permit.
2. Mỗi job có `ByteBuffer` riêng, giữ tới khi job hoàn thành. Nếu `read` chỉ chuyển một phần, `submit()` lại với offset đã tăng từ `buffer.position()` nhưng **không lấy permit mới**.
3. Nhánh `completed`, `failed` và lỗi khởi tạo đồng bộ đều đi qua `finish`; `AtomicBoolean` tránh trả permit nhiều lần.
4. `done.await()` đảm bảo các job đã báo hoàn tất trước khi chương trình đọc kết quả và đóng channel.
5. `pool.shutdown()` báo dừng executor, còn `try-with-resources` đóng channel; file tạm được dọn trong `finally`.

Với file thông thường và ba vùng 4 byte tồn tại, kết quả trên là đầu ra dự kiến. Nếu provider gặp lỗi I/O hoặc trả `0` khi buffer còn chỗ, bản demo chủ động coi là lỗi “no progress” thay vì tự retry vô hạn; kết quả là ngoại lệ thay vì stdout hoàn chỉnh.

**Giới hạn demo:** `Semaphore.acquire()` chặn **main batch producer**, điều này chủ ý để minh họa backpressure; không đưa nguyên mẫu vào thread xử lý sự kiện. Nếu producer bị interrupt hoặc phát sinh lỗi toàn cục trong khi vẫn còn I/O, application thực tế cần phối hợp dừng nhận công việc, hoàn thành/hủy những job còn lại, sau đó mới đóng tài nguyên. Demo dùng file cố định, không bao gồm queue đợi, retry policy, deadline và metrics.

## 8. Một socket không được có nhiều read pending

Với `AsynchronousSocketChannel`, mã sau sai nếu read đầu chưa hoàn tất:

```java
ByteBuffer first = ByteBuffer.allocate(1024);
ByteBuffer second = ByteBuffer.allocate(1024);

socket.read(first);  // Trả Future<Integer>
socket.read(second); // Có thể ném ReadPendingException
```

Đây là snippet có biến `socket` trong một phương thức, không phải chương trình độc lập. Tương tự, khi một write đang pending mà khởi tạo write thứ hai, có thể ném `WritePendingException`.

Mẫu đúng là **chain read tuần tự cho một socket**:

```text
start read #1
     |
     +-- completed(n > 0): parse dữ liệu, kiểm tra quota/buffer
     |                        |
     |                        +-- cần nhận tiếp: start read #2
     |
     +-- completed(-1): EOF, kết thúc input
     +-- failed(error): log/close/cleanup
```

Có thể đồng thời có **một read và một write** trên một socket. Đọc và ghi độc lập nhưng chia sẻ connection state nên phải kiểm soát việc đóng, timeout và đồng bộ trạng thái.

Đừng tạo một luồng mới cho mỗi socket chỉ để gọi `future.get()`. Với hàng nghìn socket, điều đó đánh mất nhiều lợi ích của async I/O. Callback nhanh và lập lịch hợp lý giúp phục vụ nhiều kết nối bằng một nhóm luồng có giới hạn.

## 9. ByteBuffer có quyền sở hữu trong suốt thao tác

Khi `channel.read(buffer, ...)` hoặc `channel.write(buffer, ...)` đang diễn ra, **không được tùy tiện đọc/ghi hoặc thay đổi `position`/`limit` của buffer ấy từ thread khác**. Tài liệu API nhấn mạnh `ByteBuffer` không thread-safe và phải tránh truy cập trong khi thao tác async còn pending.

Sai:

```java
Future<Integer> pending = channel.read(buffer);
buffer.clear(); // Sai: I/O có thể vẫn đang ghi vào buffer
```

Đây là snippet minh họa `AsynchronousByteChannel`, không phải `AsynchronousFileChannel` vì chữ ký đọc của file channel phải có file position. Khi chưa có completion, `clear()` có thể làm thay đổi trạng thái mà I/O đang phụ thuộc.

Cách thiết kế:

- Mỗi thao tác pending có một buffer mà nó sở hữu, hoặc một buffer pool cấp **độc quyền** tới khi completion.
- Chỉ tái sử dụng buffer sau khi I/O đã thực sự kết thúc và consumer không còn dùng dữ liệu.
- Với `slice()`/`duplicate()`, các view có thể chia sẻ storage dù có `position` riêng: không cấp đồng thời cho hai thao tác sửa cùng vùng nhớ.
- Khi partial write, buffer phải tiếp tục từ `position` hiện tại; `clear()` sớm sẽ làm mất trạng thái dữ liệu chưa gửi.
- Khi partial read của một frame, giữ state qua các completion; `read()==0` không phải EOF, `read()==-1` mới báo hết input.
- Nếu timeout khiến buffer có trạng thái chưa xác định theo hợp đồng của `AsynchronousSocketChannel`, không tái sử dụng buffer dựa trên giả định “không byte nào đã được truyền”.

Chỉ dùng `ByteBuffer.allocateDirect` khi profile thực tế cho thấy có lợi; direct buffers cũng cần quota riêng và chính sách cleanup không dựa vào `clear()` (vì `clear()` không xóa dữ liệu và không giải phóng memory).

## 10. CompletionHandler phải ngắn và luôn kết thúc tài nguyên

Callback có thể được gọi bởi thread thuộc pool xử lý async. Nếu callback thực hiện parsing rất nặng, gọi database blocking hoặc chờ một permit khác, callback có thể làm nghẽn completion của các I/O khác.

Mẫu khuyến nghị:

```text
I/O completion callback
  1) Xác nhận kết quả và trạng thái
  2) Chuyển dữ liệu/công việc tới bounded processing queue nếu cần
  3) Kết thúc quyền sở hữu I/O và giải phóng permit đúng thời điểm
  4) Lập lịch I/O tiếp theo khi có quota; tránh blocking lâu
```

Tuy nhiên, nếu queue downstream không có chỗ, **không release permit rồi tiếp tục nhận vô hạn** khi dữ liệu ứng dụng chưa được tiêu thụ. Backpressure phải xuyên suốt pipeline: khi consumer chậm, giới hạn byte đang giữ trong queue hoặc tạm dừng phát read mới trên socket.

### 10.1. Tránh “callback starvation”

Giả sử group có 4 thread và cả 4 callback đều gọi `semaphore.acquire()` để đợi slot do một callback khác sẽ `release()`. Nếu callback cần release đang chờ thread rảnh của cùng pool, ứng dụng có thể rơi vào starvation/deadlock ở mức thiết kế.

Giải pháp: **không blocking trong completion callback**. Nếu không có permit, ghi nhận trạng thái paused và nhờ scheduler hoặc queue có giới hạn tiếp tục sau khi slot được trả; nếu queue đã đầy, áp dụng policy từ chối/backpressure thay vì chờ vô hạn ngay trong pool.

### 10.2. Đảm bảo permit được trả khi failed

Mọi nhánh kết thúc logic phải xử lý:

- `completed(n)` thành công hoàn toàn.
- `completed(n)` một phần, có thể cần retry cùng job.
- `completed(-1)` EOF.
- `failed(exc)` lỗi I/O, timeout hoặc close.
- Lỗi đồng bộ khi bắt đầu I/O trước khi callback được đăng ký thành công.
- Shutdown/cancel theo quy tắc của provider.

Thiết kế một đối tượng quản lý job với trạng thái `AtomicBoolean settled` là cách giảm lỗi double-release. Với job nhiều bước, release khi **job logic** kết thúc; nếu chỉ quan tâm mỗi thao tác vật lý, cần định nghĩa rõ đơn vị quota để tránh sai số đếm.

## 11. Backpressure ở cả inbound và outbound

### Inbound: consumer chậm

Client gửi message nhanh hơn tầng parser/database xử lý. Nếu mỗi completion lập tức đọc tiếp và giữ message trong queue không giới hạn, heap tăng dù số read pending trên mỗi socket không quá một.

Các biện pháp:

1. Giới hạn số request in-flight.
2. Giới hạn **tổng byte** trong inbound queue, không chỉ số lượng frame.
3. Khi quá tải, tạm không phát read tiếp trên connection có backlog lớn, hoặc từ chối theo protocol.
4. Tiếp tục đọc khi queue đã giảm xuống dưới ngưỡng thấp (low watermark).
5. Có deadline/timeout để tránh kết nối chiếm một slot mãi.

### Outbound: peer nhận chậm

Một `AsynchronousSocketChannel.write` có thể hoàn tất với ít byte hơn `src.remaining()` ban đầu. Nhiều response có thể tích lũy trong outbound queue; cần giữ thứ tự và chỉ có **một write pending trên mỗi socket**.

```text
outbound queue: [Frame A còn dư, Frame B, Frame C]
      |
      v
write(Frame A) -> completion
    nếu còn bytes: write tiếp Frame A
    nếu hết Frame A: lấy Frame B
      |
      v
queue rỗng -> chờ message mới
```

Nếu application enqueue response nhanh hơn socket gửi, quota **outboundBytes** quan trọng hơn quota số frame. Có thể ngừng xử lý request mới, áp dụng flow control hoặc đóng các connection quá chậm theo chính sách.

Đối với async socket, đừng thử gọi `write` thứ hai khi write trước còn pending: ngoài lỗi `WritePendingException`, các buffer có thể bị quản lý sai thứ tự.

## 12. Thread pool, channel group và hàng đợi

Không chọn số worker bằng công thức “càng nhiều càng nhanh”. Tác vụ CPU-bound và I/O-bound có đặc tính khác nhau; một provider có thể dùng thread để thực hiện file I/O, một provider khác có mô hình riêng.

- Dùng thread pool phù hợp với loại workload và profile.
- Nếu callback nhẹ, một số luồng tương đối nhỏ có thể phục vụ nhiều completions.
- Nếu callback có tính toán CPU dài, chuyển chúng sang **bounded worker queue** riêng để tránh chiếm completion threads.
- Không tạo channel group hoặc executor mới cho từng request.
- Quản lý lifecycle của group/pool theo toàn dịch vụ; shutdown có trật tự, bảo đảm không nộp job mới sau khi ngừng nhận.
- `AsynchronousChannelGroup.shutdown()` và `shutdownNow()` có ngữ nghĩa khác nhau; đóng channels và chờ termination theo API khi cần. Tránh dựa vào daemon thread tự kết thúc.
- Default group/thread pool của JDK có hành vi cấu hình theo hệ thống; ứng dụng có nhu cầu tài nguyên rõ ràng nên chỉ định và đo cấu hình phù hợp.

**Điểm hay nhầm:** một executor dùng 8 thread không có nghĩa chỉ có tối đa 8 outstanding socket reads; số luồng completion cũng không phải giới hạn tổng số kết nối.

## 13. Cancellation, timeout và đóng channel

Với `Future.cancel(true)`, không nên suy luận rằng I/O đã dừng hoàn toàn và buffer ngay lập tức an toàn để sửa từ thread khác. Hành vi cancel phụ thuộc channel/provider, và cancellation có thể dẫn tới đóng channel hoặc hoàn thành với ngoại lệ.

Một số overload của `AsynchronousSocketChannel.read/write` có timeout; khi timeout xảy ra, buffer hoặc channel có thể có trạng thái phụ thuộc provider. Tài liệu API cảnh báo rằng một timeout có thể khiến kênh rơi vào trạng thái lỗi, vì hệ thống không thể xác định chắc chắn dữ liệu đã được chuyển hay chưa.

Quy trình cleanup cần phân biệt:

1. **Ngừng nhận yêu cầu mới** và dừng phát động I/O mới.
2. **Cho phép các thao tác đang có hoàn thành** trong một deadline hợp lý, hoặc áp dụng chính sách hủy.
3. **Kết thúc/đóng channel** khi đã quyết định shutdown.
4. **Bảo đảm completion/failure path cập nhật trạng thái và giải phóng permit**; không double-release.
5. **Giải phóng buffer và request state** khi chắc chắn không còn thao tác truy cập tới vùng nhớ đó.
6. Đóng channel group/executor thuộc quyền sở hữu của component; không đóng pool được thành phần khác chia sẻ một cách tùy tiện.

Với sự cố “thiếu byte” hoặc partial write, retry cả request có thể gây duplicate ở tầng ứng dụng. Nếu dữ liệu đã được gửi một phần rồi timeout, cần idempotency key, sequence number hoặc protocol xác nhận phù hợp; chỉ retry khi nghiệp vụ cho phép.

## 14. Quan sát và điều chỉnh giới hạn bằng số đo

Một hệ thống async nên có ít nhất các số liệu:

| Metric | Công dụng |
| --- | --- |
| `io.inflight` | Số thao tác thực sự chưa hoàn tất |
| `io.maxInFlight` | Giới hạn cấu hình hiện tại |
| `io.pending.requests` | Kích thước bounded queue |
| `io.pending.bytes` | Bộ nhớ/chất lượng backpressure thực |
| `io.complete.latency` | Độ trễ phát động → hoàn thành |
| `io.callback.duration` | Callback có chiếm worker quá lâu không |
| `io.errors`, `io.timeouts` | Chẩn đoán thất bại và quá tải |
| `io.rejected` | Số yêu cầu bị từ chối do hết quota |
| `process.openFiles` / sockets | Áp lực file descriptors |
| Heap/direct memory/GC | Nhìn thấy áp lực cấp phát và vùng native |

Theo dõi `p95`/`p99` latency bên cạnh throughput. Nếu tăng `MAX_IN_FLIGHT` từ 32 lên 1.024 mà throughput hầu như không tăng, trong khi queue/memory/timeout tăng mạnh, đó là dấu hiệu ứng dụng đã quá ngưỡng có lợi.

### 14.1. Little's Law và giới hạn

Với hệ thống gần trạng thái ổn định, số yêu cầu đang ở trong hệ thống xấp xỉ:

```text
L = λ × W
```

Trong đó `L` là số yêu cầu trung bình đang tồn tại, `λ` là tốc độ đến/hoàn thành trung bình, `W` là thời gian trung bình một yêu cầu ở trong hệ thống (bao gồm thời gian chờ theo định nghĩa đo). Ví dụ 500 yêu cầu/giây và latency trung bình 0,2 giây tương ứng khoảng 100 yêu cầu đang tồn tại.

Công thức **không tự cho biết số permit tối ưu**. Nó giúp ước lượng nhu cầu ở tải thực tế và nhận biết khi độ trễ tăng khiến số yêu cầu đang chờ phình to. Chọn quota còn cần xét spike, file descriptor, memory, fairness, SLA và failure modes.

## 15. Lỗi triển khai phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Phát động async read không có quota | Cạn buffer, quá tải kernel/worker | Giới hạn in-flight và byte budget |
| Tưởng 8 worker = tối đa 8 I/O | Hàng nghìn I/O vẫn có thể đang pending | Đo/giới hạn operations riêng |
| `release()` ngay sau `channel.read()` | Slot được tái sử dụng khi I/O chưa xong | Release ở completion/failure |
| Quên release trong `failed` | Rò permit, hệ thống dừng nhận công việc | Một cleanup path duy nhất |
| Callback gọi `Semaphore.acquire()` | Chặn pool, nguy cơ starvation | `tryAcquire()` hoặc scheduler có queue giới hạn |
| Tạo `ByteBuffer` rất lớn cho mỗi request | Heap/direct memory áp lực | Quota bộ nhớ và buffer phù hợp |
| Sửa/clear buffer khi Future chưa xong | Data race/corrupt byte | Quyền sở hữu buffer tới completion |
| Đọc hai lần cùng lúc trên async socket | `ReadPendingException` | Chain read sau completion |
| Ghi hai lần cùng lúc trên async socket | `WritePendingException` | Queue và serialize writes |
| Chỉ quota số item trong queue | Vài frame cực lớn vẫn làm cạn RAM | Quota theo tổng byte |
| `newFixedThreadPool` coi là queue có giới hạn | Queue task có thể tăng mãi | Tạo bounded work queue hoặc backpressure |
| Gọi `future.get()` trên thread event loop | Block event loop | CompletionHandler/callback hoặc mô hình chờ khác |
| Coi `cancel(true)` là buffer đã an toàn | Có thể vẫn còn I/O/state phụ thuộc provider | Điều phối cancel/close theo hợp đồng |
| Retry write sau timeout không xét duplicate | Gửi lặp dữ liệu/bản tin | Idempotency/sequence/acknowledgment |
| Mở executor/group cho mỗi request | Bùng nổ luồng/tài nguyên | Dùng nhóm được quản lý tập trung |

## 16. Câu hỏi tự kiểm tra

**1.** Có executor 4 thread. Có chắc chỉ tối đa 4 I/O pending?  
**Đáp án:** Không. Số thread và số I/O pending khác nhau; cần giới hạn riêng.

**2.** Phát động `read` async thành công rồi lập tức `permits.release()` có đúng không?  
**Đáp án:** Sai nếu permit đại diện cho in-flight operation; phải giữ tới completion/failure hoặc kết thúc job logic.

**3.** Có thể có hai read outstanding trên một `AsynchronousSocketChannel` không?  
**Đáp án:** Không; thao tác thứ hai ném `ReadPendingException`. Có thể có một read và một write đồng thời.

**4.** Một `AsynchronousFileChannel` có thể có nhiều read outstanding không?  
**Đáp án:** Có; API cho phép, nhưng kết quả có thể hoàn thành không theo thứ tự phát động.

**5.** Có 1.000 request với mỗi buffer 1 MiB, memory buffer xấp xỉ bao nhiêu?  
**Đáp án:** 1.000 MiB (gần 0,98 GiB), chưa tính overhead và queue khác.

**6.** Vì sao `ByteBuffer.clear()` không được gọi khi async read còn pending?  
**Đáp án:** Nó đổi `position/limit`; I/O đang dùng buffer có thể bị ảnh hưởng. Buffer không an toàn cho truy cập đồng thời khi chưa completion.

**7.** Callback chạy chậm nhưng in-flight limiter vẫn thấp. Hệ thống có thể quá tải không?  
**Đáp án:** Có. Completion pool và downstream queue/CPU cũng là nút thắt; limiter là một phần của chiến lược backpressure.

**8.** Chỉ giới hạn queue 100 message có đủ chống cạn bộ nhớ?  
**Đáp án:** Chưa chắc. Một message có thể lớn hàng chục MiB; cần giới hạn tổng byte.

**9.** `write` async hoàn thành với một phần buffer còn lại thì xử lý thế nào?  
**Đáp án:** Tiếp tục cùng buffer từ `position` còn lại khi write trước hoàn tất, không khởi tạo write chồng lấp.

**10.** `Semaphore.acquire()` trong event loop là thực hành phù hợp?  
**Đáp án:** Không. Nó có thể chặn thread; dùng `tryAcquire()` và điều phối queue/backpressure không blocking.

## 17. Checklist vận hành

1. Chọn đơn vị quota: **I/O vật lý**, **request logic**, **connection**, hoặc cả ba.
2. Tính ngân sách buffer theo số byte/operation và số slot; để dư cho heap, direct memory, TLS, outbound queues.
3. Giới hạn đồng thời cùng với bounded queue, timeout và chính sách overload.
4. Giữ permit tới completion hoặc tới khi job logic chấm dứt; cleanup đúng một lần.
5. Với asynchronous socket, duy trì tối đa một read và một write pending trên mỗi connection.
6. Quản lý quyền sở hữu `ByteBuffer` qua toàn bộ vòng đời tác vụ.
7. Không block completion handler; chuyển xử lý nặng qua bounded worker pool.
8. Kiểm soát backpressure cả inbound/outbound, nhất là khi peer gửi hoặc nhận chậm.
9. Định nghĩa shutdown/cancellation, tránh double-release và premature buffer reuse.
10. Quan sát latency p95/p99, in-flight, backlog bytes, lỗi timeout, rejection và open handles; điều chỉnh giới hạn bằng thử tải.

## Tài liệu chính thức

- Java SE 17 — `AsynchronousFileChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html
- Java SE 17 — `AsynchronousSocketChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html
- Java SE 17 — `AsynchronousChannelGroup`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html
- Java SE 17 — `CompletionHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html
- Java SE 17 — `AsynchronousByteChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousByteChannel.html
- Java SE 17 — `ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17 — `Semaphore`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html
