# Xử lý lỗi, ngắt, timeout và đóng channel trong I/O bất đồng bộ Java NIO

## 1. Tại sao I/O bất đồng bộ cần quản lý vòng đời chặt chẽ?

Các API Java NIO.2 như `AsynchronousFileChannel`, `AsynchronousSocketChannel` và `AsynchronousServerSocketChannel` cho phép bắt đầu read/write/connect/accept rồi nhận kết quả **sau đó**, thay vì bắt luồng gọi đợi thao tác hoàn tất ngay tại lời gọi.

Thao tác có thể hoàn tất thành công, thất bại, bị cancel, bị timeout, hoặc bị ảnh hưởng bởi việc đóng channel. Cần phân biệt **trạng thái Future/callback**, **tình trạng byte đã chuyển**, **quyền sử dụng ByteBuffer**, và **tình trạng kết nối/tệp**. Đây không phải cùng một khái niệm.

~~~text
Request -> submit async I/O -> PENDING
                                |   |    |
                                |   |    +-- cancel/timeout/close
                                |   +------- FAILED
                                +----------- COMPLETED
                                             |
                                       trả kết quả số byte
Sau mỗi nhánh: phân loại, kết thúc request đúng một lần,
dọn channel/buffer/attachment theo quyền sở hữu.
~~~

Không đồng nhất câu “đã gửi yêu cầu ghi” với “đã ghi đủ”, và cũng không đồng nhất “timeout chờ kết quả” với “I/O chắc chắn đã dừng”.

## 2. Future và CompletionHandler: hai mô hình nhận kết quả

### Future

~~~java
// Đoạn minh họa: file đã là AsynchronousFileChannel mở để đọc.
ByteBuffer buffer = ByteBuffer.allocate(256);
Future<Integer> pending = file.read(buffer, 0L);

int n = pending.get(); // Có thể đợi đến khi I/O kết thúc.
~~~

- `get()` chờ và trả số byte đọc/ghi; có thể ném `InterruptedException` hoặc `ExecutionException`.
- `get(timeout, unit)` có thể ném thêm `TimeoutException` khi **caller** chờ quá hạn.
- `cancel(false/true)` cố hủy computation; `isCancelled()` và `isDone()` cho biết trạng thái Future.
- Không dùng lại ByteBuffer cho operation khác trước khi có quy trình xử lý completion/cancel an toàn.

Lời gọi I/O là bất đồng bộ, nhưng `future.get()` vẫn có thể **block thread đang đợi**. Mô hình này đơn giản, nhưng gọi `get()` tuần tự cho từng request có thể làm giảm concurrency.

### CompletionHandler

~~~java
// Đoạn minh họa, chưa phải chương trình độc lập.
file.read(buffer, 0L, "req-42",
        new CompletionHandler<Integer, String>() {
            @Override
            public void completed(Integer n, String requestId) {
                System.out.println(requestId + ": " + n);
            }

            @Override
            public void failed(Throwable error, String requestId) {
                System.err.println(requestId + ": " + error);
            }
        });
~~~

`CompletionHandler<V,A>` có hai callback:

- `completed(V result, A attachment)`: hoàn tất thành công.
- `failed(Throwable exc, A attachment)`: hoàn tất thất bại.

Attachment có thể chứa request ID, trạng thái, context hoặc đối tượng điều phối. Handler được dispatch qua thread pool của async channel; trong một số trường hợp hoàn tất tức thì có thể được gọi trực tiếp từ thread khởi tạo đang thuộc pool.

**Handler nên ngắn.** Không block lâu hoặc xử lý CPU nặng trong callback pool. Chuyển công việc dài sang executor riêng nếu cần.

### Lỗi submit khác lỗi hoàn tất

Một lời gọi khởi tạo operation có thể ném lỗi ngay: tham số sai, channel chưa kết nối, read/write cùng chiều đang pending, v.v. Nếu đã khởi tạo thành công mà I/O lỗi sau đó, kết quả đi qua `failed(...)` hoặc `Future.get()`.

Chỉ bọc try/catch quanh `read(..., handler)` **không thay thế** việc triển khai `failed(...)`.

## 3. Những lỗi thường gặp và cách phân loại

| Trường hợp | Ngoại lệ/kết quả | Hành động thường phù hợp |
|---|---|---|
| Future gặp lỗi I/O | `ExecutionException` từ `get()` | Xem `getCause()`, kết thúc request lỗi |
| Handler gặp lỗi | `failed(Throwable, attachment)` | Hoàn tất promise/trạng thái lỗi |
| Caller đợi Future bị ngắt | `InterruptedException` | Khôi phục interrupt flag, xem xét cancel |
| Caller đợi quá hạn | `TimeoutException` | Đừng suy ra I/O nền đã dừng |
| Future bị cancel | `CancellationException` khi `get()` | Không báo thành công, tránh retry mù |
| File I/O đang chờ khi channel đóng | `AsynchronousCloseException` | Dọn pending request và resource |
| Channel đã đóng trước lúc gọi | `ClosedChannelException` hoặc lỗi phù hợp API | Không submit I/O mới |
| Socket chưa kết nối | `NotYetConnectedException` | Kết nối trước |
| Socket đã có một read pending | `ReadPendingException` | Không submit read chồng lấn |
| Socket đã có một write pending | `WritePendingException` | Xếp hàng write |
| Socket I/O timeout trực tiếp | `InterruptedByTimeoutException` | Cân nhắc loại bỏ buffer/channel |
| Read tới EOF | Giá trị `-1` | Phân biệt EOF hợp lệ và frame thiếu |
| Một lần read/write chỉ xử lý một phần | Số byte nhỏ hơn mong muốn | Lưu ByteBuffer position, tiếp tục đúng cách |

**Đừng bắt tất cả exception rồi retry vô hạn.** Timeout, EOF, channel close và lỗi lập trình không có cùng chính sách khôi phục.

## 4. Gỡ lỗi `ExecutionException` và xử lý lỗi từ callback

Khi dùng Future:

~~~java
// Minh họa trong phương thức có các biến và checked exceptions.
try {
    int n = pending.get();
    consume(n);
} catch (ExecutionException e) {
    Throwable root = e.getCause();
    if (root instanceof AsynchronousCloseException) {
        // Channel bị đóng khi đang xử lý.
    } else if (root instanceof IOException) {
        // Lỗi I/O file hoặc mạng.
    } else {
        // Lỗi khác: không xem là thành công.
    }
}
~~~

`consume` là hàm do ứng dụng định nghĩa. Nên ghi log root cause, request ID, file offset hoặc peer, loại operation, số byte đã biết, trạng thái channel.

Khi dùng callback, xử lý ngay `failed(Throwable, attachment)`, không dựa vào `ExecutionException` vì callback-overload không trả Future cho operation đó. Nếu code trong handler tự ném exception, lỗi đó là lỗi của logic xử lý callback; hãy bắt và chuyển về promise/trạng thái request phù hợp, tránh làm hỏng dispatcher.

### Thành công cũng cần kiểm tra số byte

Một lần `read()` có thể đọc ít hơn lượng mong đợi; `-1` nghĩa EOF. Một lần `write()` có thể chỉ ghi một phần của buffer. Không coi `completed(3)` là “đã nhận toàn bộ frame 10 byte”.

## 5. `InterruptedException`: ngắt người đợi, không tự hủy I/O

Ví dụ:

~~~java
try {
    int n = pending.get();
    use(n);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    pending.cancel(false);
    // Chuyển request sang trạng thái hủy theo chính sách.
}
~~~

Đây là đoạn minh họa, `pending` và `use` đã được định nghĩa bên ngoài.

Các điểm không được nhầm:

1. `InterruptedException` ở đây báo **thread đang chờ** Future bị interrupt.
2. Nó **không chứng minh** I/O đang thực thi ở background đã dừng hoặc chưa có byte nào được chuyển.
3. Thường khôi phục trạng thái ngắt bằng `Thread.currentThread().interrupt()` hoặc truyền exception cho tầng trên xử lý.
4. Nếu quyết định hủy, cần có bước `cancel(...)`/`close()` và kế hoạch buffer ownership.
5. Không `clear()` hoặc tái sử dụng buffer của operation đang pending vì caller đã bỏ chờ.

| Lệnh | Tác dụng chủ yếu | Không bảo đảm |
|---|---|---|
| `thread.interrupt()` | Đánh dấu ngắt thread; `get()` đang chờ có thể ném `InterruptedException` | I/O đã rollback |
| `future.cancel(false)` | Cố hủy Future, không yêu cầu interrupt task đang chạy | Không còn side effects |
| `future.cancel(true)` | Cố hủy và có thể yêu cầu interrupt task | Dừng kernel I/O ngay |
| `channel.close()` | Đóng channel, ảnh hưởng pending operations | Rollback các byte đã chuyển |

## 6. Timeout của `Future.get(timeout)` chỉ giới hạn thời gian đợi

~~~java
int n = pending.get(250, TimeUnit.MILLISECONDS);
~~~

Nếu quá hạn, thread chờ nhận `TimeoutException`, nhưng operation nền có thể vẫn đang chạy. Tình huống:

~~~text
t0: file.read(...) bắt đầu
t1: Future.get(250ms) bắt đầu chờ
t2: caller nhận TimeoutException
t3: I/O nền vẫn có thể tiếp tục và sửa ByteBuffer
t4: I/O cuối cùng hoàn tất/thất bại theo lịch riêng
~~~

Vì vậy không được trả buffer vào pool hoặc dùng cùng buffer cho thao tác mới ngay ở t2.

Một mẫu xử lý:

~~~java
// Minh họa, file và pending đã được khai báo.
try {
    int n = pending.get(250, TimeUnit.MILLISECONDS);
    consume(n);
} catch (TimeoutException e) {
    boolean cancelled = pending.cancel(false); // Best effort.
    // Không coi cancelled == true nghĩa là chưa ghi byte nào.
    // Đánh dấu request timeout; quản lý buffer/channel riêng.
}
~~~

Đây là giới hạn cho **waiter**, không phải timeout trực tiếp ở bên trong `AsynchronousFileChannel.read/write`. Các overload file read/write có offset nhưng không có tham số timeout I/O như socket.

## 7. Timeout của `AsynchronousSocketChannel`: ngữ nghĩa mạnh hơn nhưng rủi ro cao

Asynchronous socket có overload read/write callback với tham số timeout:

~~~java
// Minh họa: socket đã kết nối, dst writable.
socket.read(dst,
        500, TimeUnit.MILLISECONDS,
        requestId,
        new CompletionHandler<Integer, String>() {
            @Override
            public void completed(Integer n, String id) {
                // I/O hoàn tất.
            }

            @Override
            public void failed(Throwable error, String id) {
                if (error instanceof InterruptedByTimeoutException) {
                    // Timeout ngay trong thao tác read.
                }
                // Kết thúc request theo chính sách.
            }
        });
~~~

Theo tài liệu Java 17:

- Nếu timeout xảy ra trước khi I/O hoàn tất, handler được báo lỗi **`InterruptedByTimeoutException`**.
- Nếu triển khai không thể bảo đảm byte chưa/không còn được đọc hoặc ghi, channel có thể bị đặt vào **trạng thái lỗi đặc thù triển khai**. Read/write tiếp theo cùng chiều có thể ném runtime exception không chỉ rõ.
- **Trạng thái ByteBuffer hoặc mảng buffer sau I/O timeout là không xác định.**
- Các giá trị timeout **nhỏ hơn hoặc bằng 0** nghĩa là thao tác không timeout (không phải poll ngay).

**Cách an toàn thường dùng:** coi request/connection đã không còn tin cậy khi timeout socket mà kết quả byte không rõ, đóng channel và không tái sử dụng buffer liên quan. Nếu cần thử lại, mở kết nối mới và dùng request ID/idempotency key để tránh xử lý trùng.

### So sánh trực tiếp

| Cơ chế | Ngoại lệ | Điều đã biết khi timeout |
|---|---|---|
| `Future.get(500, MILLISECONDS)` | `TimeoutException` | Caller hết thời gian chờ; I/O có thể vẫn chạy |
| `socket.read(dst,500,MILLISECONDS,att,handler)` | `InterruptedByTimeoutException` trong `failed` | I/O báo timeout, ByteBuffer không xác định, channel có thể bị lỗi |
| Deadline nghiệp vụ tổng thể | Tùy tầng ứng dụng | Vẫn cần quyết định cancel, close, retry |

`AsynchronousSocketChannel.connect(...)` có Future và callback nhưng không cùng overload timeout như read/write; connect deadline thường do tầng điều phối quản lý.

## 8. Cancel Future không đồng nghĩa rollback

`future.cancel(mayInterruptIfRunning)` cố chuyển Future sang trạng thái canceled. Nếu hủy được chấp nhận, `isCancelled()` là true và `get()` có thể ném `CancellationException`.

Nhưng `cancel(true)` hoặc `cancel(false)` **không phải giao dịch rollback**:

- Một số byte có thể đã được OS đọc/ghi trước khi hủy.
- Peer có thể đã xử lý request dù caller không nhận kết quả.
- `ByteBuffer.position()` không phải căn cứ đủ để kết luận trạng thái giao thức sau cancel.
- Không retry một lệnh thay đổi trạng thái từ xa nếu thiếu idempotency hoặc version check.
- Nếu không thể xác định I/O đã kết thúc và buffer đã an toàn, nên cô lập hoặc loại bỏ buffer thay vì tái sử dụng ngay.

Điểm mấu chốt: **cancel là quản lý lifecycle của operation, không phải undo dữ liệu**.

## 9. Đóng channel khi còn pending operation

`AsynchronousFileChannel.close()` có thể được gọi bất cứ lúc nào. Theo hợp đồng Java 17, các operation đang outstanding trên channel sẽ hoàn tất với **`AsynchronousCloseException`**.

~~~java
// Minh họa: file là AsynchronousFileChannel.
Future<Integer> op = file.read(dst, 0L);

// Thread khác có thể gọi:
file.close();

// Thread đang get() cần chuẩn bị ExecutionException
// có cause là AsynchronousCloseException.
~~~

Đóng channel không đảm bảo những byte đã được chuyển bị hoàn tác. Nếu `isOpen()` trả true tại một thời điểm, thread khác vẫn có thể đóng ngay sau đó: kiểm tra rồi gọi I/O **không loại race**.

### Quy trình shutdown có kiểm soát

~~~text
OPEN -> CLOSING -> CLOSED
          |
          +-- không nhận thêm request mới
          +-- đánh dấu pending operations
          +-- chờ có deadline cho những operation cần thiết
          +-- cancel/close những operation còn lại
          +-- dọn callback, buffer, attachment
          +-- shutdown pool/group sở hữu
~~~

Cần thiết kế request cũng có trạng thái CREATED → PENDING → COMPLETED/FAILED/CANCELLED → CLEANED để mỗi request nhận kết quả **một lần duy nhất**. Nếu callback nhận `AsynchronousCloseException` do shutdown có chủ ý, đó có thể là một lỗi **được dự kiến**; đừng báo thành công nhưng cũng không nhất thiết xem là sự cố hệ thống.

### Ai sở hữu tài nguyên nào?

| Tài nguyên | Đóng đúng cách |
|---|---|
| `AsynchronousFileChannel` | `close()` hoặc try-with-resources |
| `AsynchronousSocketChannel` | `close()` khi request/connection hoàn tất hay lỗi |
| `AsynchronousServerSocketChannel` | `close()` để ngừng accept |
| `ExecutorService` riêng của async file | `shutdown()`, `awaitTermination(...)`; `shutdownNow()` khi cần |
| `AsynchronousChannelGroup` riêng cho async socket | `shutdown()` / `shutdownNow()` / `awaitTermination(...)` |

Trong **Java 17**, `ExecutorService` không phải `AutoCloseable`; hãy shutdown tường minh thay vì đưa executor vào try-with-resources. Không để một request shutdown pool hoặc group đang được nhiều thành phần chia sẻ.

`AsynchronousSocketChannel.shutdownInput()` / `shutdownOutput()` là half-close theo protocol, **không thay thế** đóng toàn bộ channel khi connection gặp lỗi trạng thái nghiêm trọng.

## 10. ByteBuffer ownership, I/O partial và concurrency

Các Buffer được chuyển vào asynchronous operation **không an toàn để truy cập khi operation còn pending**. Không làm:

~~~java
// Sai: cùng ByteBuffer có thể bị background read sử dụng.
ByteBuffer dst = ByteBuffer.allocate(1024);
Future<Integer> first = file.read(dst, 0L);
dst.clear();
Future<Integer> second = file.read(dst, 1024L);
~~~

Mặc dù `AsynchronousFileChannel` cho phép nhiều I/O outstanding, thứ tự I/O và thứ tự callback không được bảo đảm khi chúng đồng thời. Dùng cùng buffer cho nhiều pending operations là không an toàn. Nếu nhiều writes cùng offset, kết quả cuối không tự theo thứ tự submit.

### Async socket chỉ cho một pending read và một pending write cùng lúc

Trên một `AsynchronousSocketChannel`, có thể có một read và một write đang chờ đồng thời, nhưng:

- Read thứ hai khi read trước còn pending → `ReadPendingException`.
- Write thứ hai khi write trước còn pending → `WritePendingException`.

Duy trì queue gửi/nhận, chỉ submit I/O tiếp theo cùng chiều sau khi operation trước hoàn tất. Đừng bắt exception rồi spin retry.

### Một completion chưa chắc chuyển đủ ByteBuffer

Nếu buffer còn remaining sau read/write, có thể cần thao tác tiếp theo. Ví dụ ghi file:

~~~java
// Minh họa: file AsynchronousFileChannel, src và offset đã định nghĩa.
while (src.hasRemaining()) {
    Future<Integer> op = file.write(src, offset);
    int n = op.get();
    if (n <= 0) {
        throw new IOException("No write progress");
    }
    offset += n;
}
~~~

Không submit write tiếp lên cùng buffer trước khi Future trước kết thúc. Khi read trả `-1` nghĩa EOF; nếu phải đọc đúng N byte, EOF trước N là frame/record bị thiếu.

## 11. Chương trình Java 17+ hoàn chỉnh: Future, callback và close

Ví dụ sau không cần server mạng. Chương trình tạo file tạm, dùng `AsynchronousFileChannel`, ghi chuỗi ASCII `ABC` qua Future, đọc lại bằng CompletionHandler, đóng channel, shutdown executor và dọn file.

Lưu chính xác **`AsyncIoLifecycleDemo.java`**:

~~~java
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
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class AsyncIoLifecycleDemo {

    private static int await(Future<Integer> future)
            throws InterruptedException, ExecutionException,
                   TimeoutException {
        try {
            return future.get(5, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            future.cancel(false);
            throw e;
        } catch (TimeoutException e) {
            future.cancel(false);
            throw e;
        }
    }

    private static int writeAll(
            AsynchronousFileChannel channel, ByteBuffer src)
            throws Exception {
        long offset = 0;
        int total = 0;

        while (src.hasRemaining()) {
            Future<Integer> op = channel.write(src, offset);
            int n = await(op);
            if (n <= 0) {
                throw new IOException("No write progress");
            }
            total += n;
            offset += n;
        }
        return total;
    }

    private static CompletableFuture<String> readAll(
            AsynchronousFileChannel channel, int expectedBytes) {
        ByteBuffer dst = ByteBuffer.allocate(expectedBytes);
        CompletableFuture<String> result = new CompletableFuture<>();

        class Reader implements CompletionHandler<Integer, Void> {
            private long offset = 0;

            void start() {
                channel.read(dst, offset, null, this);
            }

            @Override
            public void completed(Integer n, Void attachment) {
                if (n < 0) {
                    result.completeExceptionally(
                            new EOFException("Truncated file"));
                    return;
                }
                if (n == 0) {
                    result.completeExceptionally(
                            new IOException("No read progress"));
                    return;
                }

                offset += n;
                if (dst.hasRemaining()) {
                    try {
                        channel.read(dst, offset, null, this);
                    } catch (RuntimeException e) {
                        result.completeExceptionally(e);
                    }
                    return;
                }

                dst.flip();
                byte[] bytes = new byte[dst.remaining()];
                dst.get(bytes);
                result.complete(new String(
                        bytes, StandardCharsets.US_ASCII));
            }

            @Override
            public void failed(Throwable error, Void attachment) {
                result.completeExceptionally(error);
            }
        }

        try {
            new Reader().start();
        } catch (RuntimeException e) {
            result.completeExceptionally(e);
        }
        return result;
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("async-io-demo-", ".bin");
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            AsynchronousFileChannel channel =
                    AsynchronousFileChannel.open(
                            file,
                            Set.of(StandardOpenOption.READ,
                                   StandardOpenOption.WRITE),
                            pool);

            try (channel) {
                ByteBuffer out = ByteBuffer.wrap(
                        "ABC".getBytes(StandardCharsets.US_ASCII));
                System.out.println(
                        "future-write=" + writeAll(channel, out));

                CompletableFuture<String> read =
                        readAll(channel, 3);
                System.out.println(
                        "callback-read=" + read.get(5, TimeUnit.SECONDS));

                System.out.println("open=" + channel.isOpen());
            }

            System.out.println("closed=" + !channel.isOpen());
        } finally {
            pool.shutdown();
            try {
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            } finally {
                Files.deleteIfExists(file);
            }
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file nguồn:

~~~bash
javac AsyncIoLifecycleDemo.java
java AsyncIoLifecycleDemo
~~~

**Stdout mong đợi khi I/O thành công, không bị interrupt/timeout:**

~~~text
future-write=3
callback-read=ABC
open=true
closed=true
~~~

Giải thích:

1. `writeAll` ghi tới khi source buffer hết remaining. Nó không giả định một write luôn ghi đủ ba byte và cập nhật offset sau mỗi completion.
2. `readAll` khởi động read callback; nếu chỉ nhận một phần thì tiếp tục ở offset kế tiếp. EOF sớm hoặc lỗi làm CompletableFuture kết thúc bằng exception.
3. `read.get(5,SECONDS)` giúp thread chính đợi kết quả callback thực tế. Dùng `Thread.sleep(...)` để đoán callback đã chạy hay chưa sẽ không đáng tin.
4. `isOpen()` là true trước khi rời try-with-resources. Sau khi `close()` được gọi tự động, `isOpen()` là false.
5. Executor do chương trình sở hữu được shutdown sau khi channel đóng, rồi file tạm được xóa.

Nếu có timeout ở bước đợi callback, try-with-resources sẽ đóng channel trước cleanup; điều này **không đồng nghĩa rollback** một operation đã chuyển byte. Ví dụ có đường thành công ổn định thay vì cố tạo race bằng sleep.

## 12. Mẫu Future timeout và interrupt có trách nhiệm

~~~java
// Minh họa: file là AsynchronousFileChannel,
// dst thuộc riêng operation này.
Future<Integer> op = file.read(dst, 0L);

try {
    int n = op.get(200, TimeUnit.MILLISECONDS);
    consume(n);
} catch (TimeoutException e) {
    op.cancel(false);
    // Không dùng lại dst ngay.
    // Owner quyết định đóng/cô lập channel hoặc cleanup.
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    op.cancel(false);
} catch (ExecutionException e) {
    logFailure(e.getCause());
}
~~~

`consume` và `logFailure` là hàm ứng dụng định nghĩa. Nếu `file` là channel **dùng chung cho nhiều request**, không đóng toàn bộ channel chỉ vì một request timeout trừ khi có chính sách tác động tới mọi request liên quan. Cần quản lý lifecycle và ownership rõ ràng từ đầu.

## 13. Mẫu timeout socket với CompletionHandler

~~~java
// Minh họa: socket đã kết nối; RequestContext do ứng dụng tạo.
socket.read(dst, 500, TimeUnit.MILLISECONDS,
        context,
        new CompletionHandler<Integer, RequestContext>() {
            @Override
            public void completed(Integer n, RequestContext ctx) {
                if (n < 0) {
                    ctx.peerClosed();
                } else {
                    ctx.readCompleted(n);
                }
            }

            @Override
            public void failed(Throwable error, RequestContext ctx) {
                ctx.failed(error);
                // Với InterruptedByTimeoutException:
                // không dựa vào trạng thái cũ của buffer/channel.
            }
        });
~~~

Đoạn code này không độc lập; `RequestContext` và `ctx.*` là cấu trúc do ứng dụng định nghĩa. Callback cần đảm bảo request chỉ được báo hoàn tất/thất bại **một lần**, và shutdown không chạy đua với callback để dọn cùng buffer hai lần.

## 14. Thread pool, AsynchronousChannelGroup và shutdown

`AsynchronousFileChannel.open(...)` có thể nhận một `ExecutorService`. Các asynchronous socket channels có thể dùng `AsynchronousChannelGroup` để xử lý callback và tài nguyên I/O liên quan.

| API | Ý nghĩa |
|---|---|
| `ExecutorService.shutdown()` | Ngừng nhận task mới; task đã nhận có thể tiếp tục |
| `ExecutorService.shutdownNow()` | Cố ngắt các task đang thực thi, không đảm bảo dừng ngay |
| `ExecutorService.awaitTermination(...)` | Đợi có timeout cho pool kết thúc |
| `AsynchronousChannelGroup.shutdown()` | Bắt đầu graceful shutdown theo hợp đồng |
| `AsynchronousChannelGroup.shutdownNow()` | Cố shutdown ngay, đóng các channel thuộc group |
| `AsynchronousChannelGroup.awaitTermination(...)` | Đợi group chấm dứt |

Không block callback quá lâu bằng `Future.get()` cho I/O khác cũng phụ thuộc cùng pool nhỏ: dễ gây **thread starvation**. Chỉ thành phần **sở hữu** group/pool mới được shutdown, tránh phá các channel dùng chung.

## 15. Checklist ứng dụng production

1. Mỗi request có state rõ ràng: CREATED → PENDING → COMPLETED/FAILED/CANCELLED → CLEANED.
2. Chỉ dùng ByteBuffer sau khi operation hoàn tất và ownership được trả lại một cách hợp lệ.
3. Luôn xử lý partial read/write, EOF và số byte thực tế.
4. Với Future, lấy lỗi gốc từ `ExecutionException.getCause()`; với handler, cài `failed(...)`.
5. Phân biệt timeout người đợi, timeout I/O socket và deadline nghiệp vụ tổng thể.
6. Khi bắt `InterruptedException`, truyền lên hoặc khôi phục interrupt flag.
7. Cancel không phải rollback; retry có version/idempotency khi có side effect.
8. Với socket, giữ tối đa một read và một write cùng chiều pending theo hợp đồng.
9. Ngừng nhận request mới trước shutdown; đóng channel và xử lý mọi pending callback/future.
10. Không shutdown executor hoặc group dùng chung bởi một request riêng lẻ.
11. Log request ID, operation, offset/peer, timeout, lỗi gốc và trạng thái cleanup.
12. Test EOF, partial I/O, timeout, interrupt, cancel, close khi pending và race lúc shutdown.

## 16. Những lỗi tư duy thường gặp

| Ngộ nhận | Sự thật |
|---|---|
| “Async method trả về tức là I/O xong” | Đợi Future hoặc callback. |
| “`Future.get(timeout)` timeout là I/O dừng” | Chỉ waiter hết hạn; nền có thể tiếp tục. |
| “Ngắt thread đợi là rollback operation” | Không rollback. |
| “`cancel(true)` chắc chắn chưa ghi byte nào” | Không có bảo đảm đó. |
| “Socket timeout giữ buffer nguyên vẹn” | Trạng thái buffer không xác định. |
| “Sau socket timeout luôn retry cùng channel” | Channel có thể ở trạng thái lỗi. |
| “Callback luôn ở thread caller” | Callback liên quan pool; có điều kiện chạy trực tiếp. |
| “Chỉ bắt exception lúc submit là đủ” | Phải xử lý lỗi hoàn tất qua Future/handler. |
| “Close channel undo dữ liệu” | Close không phải transaction rollback. |
| “File async write hoàn tất theo thứ tự submit” | Thứ tự khi concurrent không được hứa. |
| “Async socket cho nhiều read pending” | Có thể ném `ReadPendingException`. |
| “Buffer có thể clear trước khi callback” | Không an toàn khi pending. |
| “Java 17 ExecutorService tự close bằng try-with-resources” | Không; shutdown tường minh. |

## 17. Tự kiểm tra

1. `get(100, MILLISECONDS)` ném `TimeoutException`, I/O còn chạy không? **Có thể.**
2. `InterruptedException` có xác nhận zero bytes transferred không? **Không.**
3. Future thất bại có thể tìm nguyên nhân bằng gì? **`ExecutionException.getCause()`.**
4. Callback báo thất bại qua đâu? **`CompletionHandler.failed(...)`.**
5. Socket I/O timeout trực tiếp báo exception gì? **`InterruptedByTimeoutException`.**
6. Trạng thái buffer sau socket I/O timeout có chắc ổn không? **Không xác định.**
7. Cancel Future có transaction rollback không? **Không.**
8. `AsynchronousFileChannel` có file pointer chung không? **Không; offset cho từng operation.**
9. Đóng async file lúc pending read/write dẫn tới lỗi nào? **`AsynchronousCloseException`.**
10. Submit hai pending reads trên một socket async? **Có thể `ReadPendingException`.**
11. Completion báo 2 byte nhưng cần 8 byte có xong chưa? **Chưa.**
12. Có nên một request tự shutdown shared executor không? **Không.**
13. Timeout một request đã gửi từ xa có thể retry mù không? **Không; cần kiểm tra/idempotency.**

## 18. Tài liệu chính thức Java SE 17

- [AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): Future, CompletionHandler, close, offsets và ordering.
- [AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): timeout I/O, pending limits và trạng thái buffer.
- [CompletionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): completed/failed.
- [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): get, get(timeout), cancel.
- [AsynchronousChannelGroup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html): lifecycle và shutdown.
- [AsynchronousCloseException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousCloseException.html): pending operation và close.
- [InterruptedByTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/InterruptedByTimeoutException.html): socket I/O timeout.
