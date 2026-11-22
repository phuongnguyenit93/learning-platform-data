# Kết quả `Future` và callback `CompletionHandler` khi dùng `AsynchronousFileChannel`

## 1. Hai mô hình nhận kết quả bất đồng bộ

Đọc hoặc ghi file có thể mất thời gian vì tốc độ lưu trữ, cache, quyền truy cập, truy cập mạng hoặc các tiến trình khác. Với Java NIO.2, `AsynchronousFileChannel` cho phép **khởi tạo** một thao tác đọc/ghi tại vị trí file được chỉ định và **nhận kết quả sau khi thao tác hoàn tất**, theo hai mô hình:

- **`Future<Integer>`:** lời gọi trả về đối tượng đại diện kết quả đang chờ. Caller dùng `isDone()`, `get()` hoặc `get(timeout, unit)` để kiểm tra/chờ và nhận số byte đã truyền.
- **`CompletionHandler<Integer, A>`:** caller truyền callback; Java gọi `completed(Integer result, A attachment)` khi I/O thành công hoặc `failed(Throwable error, A attachment)` khi nó thất bại.

~~~java
// Cách 1: trả về Future<Integer>.
Future<Integer> pendingRead = channel.read(readBuffer, 0L);

// Cách 2: đăng ký callback, không trả Future.
channel.read(readBuffer, 0L, attachment, handler);
~~~

Đây là **hai ví dụ độc lập về chữ ký API**: không khởi tạo chúng đồng thời trên cùng `ByteBuffer`. Cần `AsynchronousFileChannel channel` đang mở để đọc, `ByteBuffer readBuffer`, `attachment` và `handler` có kiểu thích hợp. **Cả hai cách đều bất đồng bộ ở thời điểm khởi tạo**, nhưng caller chọn **cách tiêu thụ kết quả** khác nhau.

**Đề bài:** “Kết quả Future và callback CompletionHandler”, trong nhóm “Kênh tệp bất đồng bộ”. Bài tập trung vào kết quả, callback, luồng thực thi, partial I/O, offset và buffer. Các thao tác `AsynchronousFileChannel` được sử dụng đều thuộc API NIO.2 từ Java 7 và **vẫn được hỗ trợ trên Java 17/21 và những JDK hiện đại**. `CompletableFuture` được dùng như **adapter** trong ví dụ Java 21, không phải kiểu `read`/`write` mặc định trả về. Nội dung tuân thủ Special Note: chỉ trình bày API/quy tắc vẫn còn áp dụng, không đề xuất kiến thức legacy.

### Mục tiêu

1. Phân biệt chính xác overload `read`/`write` dạng Future và dạng callback.
2. Hiểu `Integer` kết quả, `-1` khi đọc EOF, và vì sao một lần I/O có thể chỉ truyền một phần.
3. Biết `Future.get` có thể chặn, timeout không hủy I/O, và các nhóm exception.
4. Dùng `CompletionHandler.completed`/`failed` với `attachment` để xử lý nhiều request có ngữ cảnh riêng.
5. Kiểm soát `ByteBuffer`, `position`, `limit`, `flip()` và thời gian sống buffer trong asynchronous I/O.
6. Hiểu thread pool, không có thứ tự completion bảo đảm, cách đóng/cancel an toàn.
7. Chạy được chương trình Java 21 ghi/đọc file bằng cả hai cách, có stdout xác minh trên hệ thống file thật.
8. Biết lỗi thường gặp và thiết kế phù hợp khi cần độ bền dữ liệu, hiệu năng, bảo mật.

## 2. Sơ đồ Future và CompletionHandler

~~~text
                 AsynchronousFileChannel
                           |
              read/write(ByteBuffer, offset)
                           |
             +-------------+------------------+
             |                                |
       Future<Integer>                 CompletionHandler<Integer,A>
             |                                |
      caller làm việc khác            handler đã đăng ký
             |                                |
        get()/isDone()               completed(count, attachment)
             |                      hoặc failed(error, attachment)
             |                                |
      nhận count hoặc lỗi             nhận count hoặc lỗi
             +----------------+---------------+
                              |
            cập nhật offset, xử lý bytes/lỗi,
               kết thúc hoặc submit tiếp
~~~

| Tiêu chí | `Future<Integer>` | `CompletionHandler<Integer,A>` |
| --- | --- | --- |
| Chữ ký chính | `read(buffer, position)` / `write(buffer, position)` | `read(buffer, position, attachment, handler)` / `write(...)` |
| Kiểu trả về | `Future<Integer>` | `void` |
| Khi nào có số byte? | Khi future hoàn tất, lấy bằng `get()` | Java gọi `completed(Integer count, A attachment)` |
| Lỗi khi I/O pending thất bại | `ExecutionException.getCause()` sau `get` | `failed(Throwable error, A attachment)` |
| Chờ với timeout | `get(timeout, unit)` | Phải tự thiết kế timeout/khóa trạng thái nếu cần |
| Ngữ cảnh request | Lưu trong object/biến của caller | `attachment` đi tới callback |
| Thread tiêu thụ kết quả | Thread gọi `get()` hoặc cơ chế phối hợp ngoài | Thread trong pool gắn với channel |
| Rủi ro thường gặp | `get()` chặn caller, tưởng timeout đã hủy I/O | Callback làm việc nặng, không xử lý `failed` hoặc partial read/write |

**Không có `Future.get()` nào được gọi tự động trong overload handler.** Khi bạn muốn dùng cả callback và promise, phải tạo `CompletableFuture` hoặc một loại request-result khác trong code của ứng dụng.

## 3. Mở kênh và các open options

~~~java
try (AsynchronousFileChannel channel = AsynchronousFileChannel.open(
        file,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE,
        StandardOpenOption.CREATE_NEW)) {
    // Khởi tạo Future hoặc callback trong vòng đời channel.
}
~~~

Đây là ví dụ minh họa, với `Path file` được chọn an toàn; cần import `java.nio.channels.AsynchronousFileChannel`, `Path`, `StandardOpenOption` và xử lý `IOException`.

Những options được dùng phổ biến:

| Option | Ý nghĩa |
| --- | --- |
| `READ` | Mở kênh cho phép đọc |
| `WRITE` | Mở kênh cho phép ghi |
| `CREATE` | Tạo file nếu chưa có; nếu đã có thì mở file đang tồn tại |
| `CREATE_NEW` | Tạo file mới và thất bại khi tên đã tồn tại |
| `TRUNCATE_EXISTING` | Xóa nội dung đã có khi mở để ghi |
| `DELETE_ON_CLOSE` | Provider cố gắng xóa khi đóng kênh |
| `SYNC` / `DSYNC` | Yêu cầu đồng bộ cập nhật theo file system |
| `SPARSE` | Gợi ý tạo sparse file khi được hỗ trợ |

Lưu ý `CREATE` và `TRUNCATE_EXISTING` có thể ảnh hưởng file đã tồn tại. Bài thực hành dùng `CREATE_NEW` trong thư mục tạm riêng. `AsynchronousFileChannel` **không có vị trí ghi chung để tự APPEND**; mỗi read/write nhận offset riêng. Không dùng `size()` cộng `write(...)` để coi đó là atomic append giữa nhiều writers.

### 3.1. Pool thực thi

Ngoài overload varargs đơn giản, Java có factory nhận `Set<? extends OpenOption>`, `ExecutorService` và thuộc tính tạo file tùy chọn:

~~~java
AsynchronousFileChannel channel = AsynchronousFileChannel.open(
        file,
        Set.of(StandardOpenOption.READ, StandardOpenOption.WRITE),
        executor);
~~~

Đây là đoạn minh họa với `ExecutorService executor` đã được chuẩn bị; code cần quản lý vòng đời `channel` và `executor` riêng. Pool gắn với channel hỗ trợ xử lý I/O và gọi completion handlers. Nếu dùng overload đơn giản, JDK chọn **default pool phụ thuộc implementation**, có thể được chia sẻ.

Theo Javadoc Java SE 21, **CompletionHandler của channel được gọi trên một thread thuộc pool gắn với channel**. Nếu request hoàn thành ngay và thread khởi tạo chính là một thread trong pool, callback có thể được gọi trực tiếp bởi thread đó. Không dựa vào việc callback luôn chạy trên thread main hoặc callback của hai thao tác chạy theo thứ tự khởi tạo.

Mặc dù channel dùng được từ nhiều thread, **ByteBuffer không an toàn để dùng cho nhiều I/O đang pending đồng thời**. Luôn cấp buffer riêng theo request hoặc serialize những lần dùng một buffer.

## 4. File offset không phải ByteBuffer position

`AsynchronousFileChannel` **không có current file position**. Mỗi thao tác yêu cầu một `long position`:

~~~java
Future<Integer> a = channel.read(bufferA, 0L);
Future<Integer> b = channel.read(bufferB, 4096L);
~~~

Đây là đoạn minh họa với hai buffer **khác nhau**, nếu cùng pending. `0L` là byte đầu file, `4096L` là byte ở index 4096.

Với một write bắt đầu ở offset 100, còn 12 byte trong buffer, nếu lần đầu ghi được 5 byte:

~~~text
Trước ghi:  fileOffset = 100, buffer.remaining = 12
Sau ghi:    count = 5
Tiếp theo:  fileOffset = 105, buffer.remaining = 7
~~~

**Cả hai vị trí phải được xử lý đúng:**

- `fileOffset` là vị trí byte trong file truyền cho `read/write`.
- `buffer.position()` được cập nhật theo bytes đã truyền trong buffer.
- Khi request hoàn tất một phần, tiếp tục từ `offset + count` và cùng buffer **sau khi completion của request trước**.

Đừng lặp lại write ở offset 100 với buffer đã tiến, vì như vậy có thể ghi đè vùng đã ghi. Đừng nghĩ một operation thành công đồng nghĩa toàn bộ buffer đã được truyền.

Nếu write ở offset vượt quá file size, file có thể được mở rộng; các bytes nằm trong khoảng trống giữa EOF trước đó và bytes mới ghi có **giá trị không được API bảo đảm**. Không giả định gap luôn là bytes zero trên mọi provider.

## 5. `Future<Integer>`: nhận kết quả bằng get

Hai overload:

~~~java
Future<Integer> readFuture = channel.read(destination, filePosition);
Future<Integer> writeFuture = channel.write(source, filePosition);
~~~

`destination` và `source` là hai `ByteBuffer` thích hợp, `filePosition >= 0` và channel có quyền tương ứng. Các lệnh trả Future cho các thao tác đang chờ. Khi gọi:

~~~java
int count = readFuture.get();
~~~

`get()` **có thể chặn thread gọi** cho tới khi I/O hoàn tất. API là asynchronous nhưng code gọi `get()` ngay có thể khiến caller chờ tương tự một thao tác đồng bộ.

### 5.1. Timeout

~~~java
int count = readFuture.get(5, TimeUnit.SECONDS);
~~~

Nếu sau 5 giây chưa có kết quả, `get` ném `TimeoutException`. **Nó không tự gọi `cancel` và không bảo đảm I/O đã ngừng.** Vì vậy không tái dùng `ByteBuffer` đang pending ngay sau timeout.

### 5.2. Các exception khi dùng Future

| Trạng thái | `get()` |
| --- | --- |
| Hoàn tất thành công | Trả `Integer` (số bytes hoặc `-1` của read) |
| Hoàn tất thất bại | `ExecutionException` chứa cause I/O thực |
| Thread đang chờ bị interrupt | `InterruptedException` |
| Đợi có timeout nhưng hết thời gian | `TimeoutException` |
| Future đã bị hủy | `CancellationException` |

Ví dụ xử lý:

~~~java
try {
    int count = readFuture.get(5, TimeUnit.SECONDS);
    // Xử lý count.
} catch (TimeoutException ex) {
    // Chờ quá lâu; I/O có thể vẫn đang chạy.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Thoát hoặc propagate interruption.
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    // Xử lý lỗi thật, ví dụ IOException.
} catch (CancellationException ex) {
    // Future bị hủy.
}
~~~

Đây là đoạn minh họa; cần import các lớp `java.util.concurrent` tương ứng, và thực hiện chính sách application trong từng nhánh. **Không âm thầm bắt exception rồi coi file không có nội dung**.

`Future.isDone()` không chỉ báo “thành công”: nó true khi kết quả hoàn tất, thất bại hoặc bị hủy. `Future.isCancelled()` chỉ báo trạng thái hủy, không chứng minh bytes chưa được chuyển trong I/O thực.

### 5.3. EOF và kết quả 0

- `count > 0`: số bytes đã truyền trong read/write đó.
- `count == 0`: không truyền byte; không được coi là EOF. Cần chính sách retry/backoff hoặc fail-fast nếu không tiến triển.
- `count == -1` với **read**: đã tới cuối file tại vị trí được kiểm tra trong thao tác đó.
- `write` không dùng `-1` như mã EOF thông thường.

Một buffer còn 100 byte có thể nhận ít hơn 100 byte ở **một** completion. Điều này cần được xử lý dù Future đã hoàn tất bình thường.

### 5.4. Future không mặc nhiên là CompletableFuture

`channel.read(buffer, offset)` chỉ hứa `Future<Integer>`. **Đừng ép kiểu** kết quả sang `CompletableFuture<Integer>` rồi gọi `thenApply`. Muốn composition, dùng executor/chức năng phù hợp hoặc **tự chuyển callback sang CompletableFuture**. Chương trình hoàn chỉnh sẽ làm việc này đúng cách.

## 6. `CompletionHandler`: kết quả qua completed và failed

API nhận callback:

~~~java
channel.read(destination, 0L, requestId,
        new CompletionHandler<Integer, String>() {
            @Override
            public void completed(Integer count, String attachment) {
                // Thành công: count là số byte đọc (hoặc -1 khi EOF).
            }

            @Override
            public void failed(Throwable error, String attachment) {
                // Báo lỗi I/O với ngữ cảnh requestId.
            }
        });
~~~

Đây là đoạn minh họa với `destination`, `requestId` và channel phù hợp. Chữ ký tổng quát:

~~~java
<A> void read(ByteBuffer dst, long position,
              A attachment,
              CompletionHandler<Integer, ? super A> handler);

<A> void write(ByteBuffer src, long position,
               A attachment,
               CompletionHandler<Integer, ? super A> handler);
~~~

Tham số `A attachment` là ngữ cảnh đi theo operation, giúp callback dùng chung nhận biết mỗi request: ID công việc, buffer, file offset tiếp theo, tổng bytes đã xử lý hoặc promise. Generic `V` của `CompletionHandler<V,A>` ở đây là `Integer`, còn `A` do ứng dụng chọn.

### 6.1. Nghĩ đúng về callback

- `completed(result, attachment)` nghĩa **một operation đã thành công**, không hứa toàn bộ logical file đã được truyền.
- `failed(error, attachment)` nghĩa **operation thất bại**; phải báo/lưu lỗi để caller không chờ mãi.
- Callback được thực hiện bởi thread trong pool, cần **hoàn thành nhanh**, không block lâu bằng việc đợi các Future khác trong chính pool.
- Không dự đoán thứ tự callback nếu có nhiều operations pending.
- Khi callback tạo operation tiếp theo trên cùng buffer, phải làm sau completion của lượt trước, và cập nhật file offset theo count.
- Một handler được dùng chung nhiều request vẫn cần quản lý mutable attachment/thread-safety.

### 6.2. Ví dụ attachment riêng

~~~java
record Request(String id, long offset) {}

Request request = new Request("task-17", 0L);
channel.read(buffer, request.offset(), request, handler);
~~~

Đây là minh họa với Java hiện đại, `handler` có generic `CompletionHandler<Integer,Request>`. Record này chỉ chứa metadata; khi xử lý partial I/O, state thực còn có thể cần `ByteBuffer`, counter và kết quả cuối. Attachment **không tự động làm code thread-safe**.

## 7. Vòng đời của ByteBuffer

Để ghi:

~~~java
byte[] bytes = "Hello".getBytes(StandardCharsets.UTF_8);
ByteBuffer source = ByteBuffer.wrap(bytes);
Future<Integer> pending = channel.write(source, 0L);
~~~

`ByteBuffer.wrap` dùng chính mảng byte. Sau khi initiate, **không sửa mảng, không đọc/chỉnh vị trí hay nội dung buffer** cho đến khi operation hoàn tất.

Để đọc:

~~~java
ByteBuffer destination = ByteBuffer.allocate(5);
int count = channel.read(destination, 0L).get();
if (count >= 0) {
    destination.flip();
    String text = StandardCharsets.UTF_8.decode(destination).toString();
}
~~~

Đây là minh họa; phải xử lý exceptions `get`, trường hợp read không đủ 5 bytes và charset. Khi đọc:

1. `allocate(5)` cho capacity 5, position ban đầu 0.
2. I/O đặt bytes vào buffer và tăng position.
3. `flip()` chuyển sang chế độ tiêu thụ: limit = position cũ, position = 0.
4. `decode` diễn giải bytes thành text.

Với UTF-8, **số byte không nhất thiết bằng số ký tự Java**. Nếu giải mã nhiều chunk có ký tự nhiều byte bị chia tại ranh giới, cần dùng `CharsetDecoder` stateful hoặc ghép đủ bytes trước khi decode, không ép từng chunk thành chuỗi độc lập.

### 7.1. Partial I/O không hiếm về mặt hợp đồng

Ví dụ một write còn 12 bytes nhưng callback báo count 5. Cần ghi 7 bytes còn lại từ offset cũ + 5. Không dùng `ByteBuffer.clear()` giữa hai lượt để bắt đầu lại từ đầu. Mục tiêu là **hoàn thành một logical transfer** bằng nhiều operations nếu cần.

~~~java
long offset = 0L;
while (source.hasRemaining()) {
    int n = channel.write(source, offset).get(5, TimeUnit.SECONDS);
    if (n <= 0) {
        throw new IOException("No forward progress");
    }
    offset += n;
}
~~~

Đây là helper minh họa có policy **fail fast khi 0 byte**; một ứng dụng lớn có thể thiết kế retry/backoff/deadline, không retry vô hạn. Quan trọng: mỗi operation được đợi hoàn tất trước khi tiếp tục dùng **cùng** source buffer.

## 8. Chương trình Java 21 hoàn chỉnh có cả Future và CompletionHandler

Bài thử tạo một thư mục tạm mới và file `message.txt` trong đó. Trình tự:

1. Mở `AsynchronousFileChannel` với `READ`, `WRITE`, `CREATE_NEW`.
2. Dùng Future ghi chuỗi `"Future"` (6 byte) tại offset 0.
3. Dùng Future đọc lại 6 byte, `flip()` và decode UTF-8.
4. Dùng CompletionHandler ghi `"|Callback"` (9 byte) từ offset 6. Nếu ghi từng phần, handler tự submit tiếp từ offset mới.
5. Dùng CompletionHandler đọc lại 9 byte từ offset 6.
6. Kiểm tra EOF bằng Future read tại offset 15.
7. Đóng channel, đọc lại file thật để kiểm chứng nội dung `Future|Callback`, rồi dọn file/thư mục tạm.

Để main test đợi callback hoàn tất **một cách có thời hạn**, code xây một adapter `CompletableFuture<Integer>` **riêng** rồi hoàn tất nó trong `completed`/`failed`. Đây không phải kiểu mặc định trả về từ overload handler.

Tạo file `src/main/java/demo/FutureAndHandlerExample.java`:

~~~java
package demo;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.CompletionHandler;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public final class FutureAndHandlerExample {
    private FutureAndHandlerExample() {}

    private static final class Transfer {
        final ByteBuffer buffer;
        final CompletableFuture<Integer> completion = new CompletableFuture<>();
        long offset;
        int transferred;
        int emptyCompletions;

        Transfer(ByteBuffer buffer, long offset) {
            this.buffer = buffer;
            this.offset = offset;
        }
    }

    static int writeAllFuture(AsynchronousFileChannel channel,
                              ByteBuffer source, long offset)
            throws Exception {
        int total = 0;
        while (source.hasRemaining()) {
            int count = channel.write(source, offset + total)
                    .get(5, TimeUnit.SECONDS);
            if (count <= 0) {
                throw new IOException("No progress while writing");
            }
            total += count;
        }
        return total;
    }

    static int readAllFuture(AsynchronousFileChannel channel,
                             ByteBuffer target, long offset)
            throws Exception {
        int total = 0;
        while (target.hasRemaining()) {
            int count = channel.read(target, offset + total)
                    .get(5, TimeUnit.SECONDS);
            if (count == -1) {
                return total == 0 ? -1 : total;
            }
            if (count == 0) {
                throw new IOException("No progress while reading");
            }
            total += count;
        }
        return total;
    }

    static CompletableFuture<Integer> transferWithHandler(
            AsynchronousFileChannel channel, ByteBuffer buffer,
            long offset, boolean writing) {
        Transfer state = new Transfer(buffer, offset);
        if (!buffer.hasRemaining()) {
            state.completion.complete(0);
            return state.completion;
        }

        final class Handler implements CompletionHandler<Integer, Transfer> {
            void submit(Transfer request) {
                try {
                    if (writing) {
                        channel.write(request.buffer, request.offset, request, this);
                    } else {
                        channel.read(request.buffer, request.offset, request, this);
                    }
                } catch (RuntimeException exc) {
                    failed(exc, request);
                }
            }

            @Override
            public void completed(Integer count, Transfer request) {
                if (count == -1 && !writing) {
                    request.completion.complete(
                            request.transferred == 0 ? -1 : request.transferred);
                    return;
                }
                if (count == null || count < 0) {
                    failed(new IOException("Unexpected transfer count"), request);
                    return;
                }
                if (count == 0) {
                    if (++request.emptyCompletions > 5) {
                        failed(new IOException("No I/O progress"), request);
                    } else {
                        submit(request);
                    }
                    return;
                }

                request.emptyCompletions = 0;
                request.transferred += count;
                request.offset += count;

                if (request.buffer.hasRemaining()) {
                    submit(request);
                } else {
                    request.completion.complete(request.transferred);
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
        Path directory = Files.createTempDirectory("async-future-handler-");
        Path file = directory.resolve("message.txt");

        try {
            try (AsynchronousFileChannel channel = AsynchronousFileChannel.open(
                    file,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.CREATE_NEW)) {

                byte[] futureBytes = "Future".getBytes(StandardCharsets.UTF_8);
                int futureWritten = writeAllFuture(
                        channel, ByteBuffer.wrap(futureBytes), 0);
                System.out.println("future-write=" + futureWritten);

                ByteBuffer first = ByteBuffer.allocate(futureBytes.length);
                int futureRead = readAllFuture(channel, first, 0);
                first.flip();
                System.out.println("future-read-bytes=" + futureRead);
                System.out.println("future-text="
                        + StandardCharsets.UTF_8.decode(first));

                byte[] callbackBytes = "|Callback".getBytes(StandardCharsets.UTF_8);
                int handlerWritten = transferWithHandler(channel,
                        ByteBuffer.wrap(callbackBytes), futureBytes.length, true)
                        .get(5, TimeUnit.SECONDS);
                System.out.println("handler-write=" + handlerWritten);

                ByteBuffer second = ByteBuffer.allocate(callbackBytes.length);
                int handlerRead = transferWithHandler(channel, second,
                        futureBytes.length, false).get(5, TimeUnit.SECONDS);
                second.flip();
                System.out.println("handler-read-bytes=" + handlerRead);
                System.out.println("handler-text="
                        + StandardCharsets.UTF_8.decode(second));

                int endOfFile = channel.read(ByteBuffer.allocate(4),
                        futureBytes.length + callbackBytes.length)
                        .get(5, TimeUnit.SECONDS);
                System.out.println("eof=" + endOfFile);
                System.out.println("channel-size=" + channel.size());
            }

            System.out.println("on-disk="
                    + Files.readString(file, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa `src/` bằng JDK 21:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/FutureAndHandlerExample.java
java -cp out demo.FutureAndHandlerExample
~~~

**Stdout chính xác đã kiểm thử trên default Windows filesystem với Java 21:**

~~~text
future-write=6
future-read-bytes=6
future-text=Future
handler-write=9
handler-read-bytes=9
handler-text=|Callback
eof=-1
channel-size=15
on-disk=Future|Callback
~~~

### 8.1. Diễn giải stdout

| Kết quả | Giải thích |
| --- | --- |
| `future-write=6` | Future write và helper vòng lặp ghi đủ 6 bytes ở offset 0 |
| `future-read-bytes=6` | Future read lấy đủ 6 bytes, không đọc sẵn từ `String` |
| `future-text=Future` | `flip()` rồi UTF-8 decode cho nội dung phần thứ nhất |
| `handler-write=9` | Callback write hoàn thành 9 bytes của `"|Callback"` ở offset 6 |
| `handler-read-bytes=9` | Callback read lấy đủ 9 bytes ở offset 6 |
| `handler-text=\|Callback` | Phần thứ hai đúng sau decode |
| `eof=-1` | Thử đọc tại offset 15 khi file không thay đổi, nhận EOF |
| `channel-size=15` | File có 15 bytes: 6 + 9 |
| `on-disk=Future\|Callback` | Đóng kênh xong, đọc file thực xác nhận nội dung được ghi |

Đây là stdout **đã quan sát ở môi trường kiểm thử**, không là bảo đảm thời gian hoàn tất, số lần callback hoặc thứ tự thực thi bên trong cho mọi provider. Lớp adapter helper giúp kết quả logic đúng khi I/O có partial completion.

### 8.2. Đọc helper Future

`writeAllFuture` không coi một `Future.get()` thành công là toàn bộ buffer đã ghi. Mỗi lần trả count dương, nó tăng `total`, tự cập nhật file offset cho lần tiếp và chỉ dùng buffer sau completion. `readAllFuture` xử lý `-1` riêng và trả số bytes đã đọc nếu EOF đến sau một phần.

Cả hai helper trong ví dụ chọn **fail-fast khi count 0** để tránh vòng không tiến triển. Đối với hệ thống có provider trả 0 tạm thời, có thể dùng retry/backoff và deadline tổng; không nên spin vô hạn.

### 8.3. Đọc helper CompletionHandler

`Transfer` là **attachment/state** của một logical request, giữ:

- Buffer chỉ thuộc request đó.
- Offset trong file cho thao tác kế.
- Tổng bytes đã hoàn thành.
- Số completions không tiến triển để tránh retry vô hạn.
- Một `CompletableFuture<Integer>` do **ứng dụng tạo** để truyền outcome cho main.

Handler gọi `completed` với một count; nếu còn bytes trong buffer, handler submit **operation tiếp theo** sau completion trước, và cập nhật offset. Khi đủ, gọi `completion.complete(total)`. Với `failed`, gọi `completeExceptionally(error)`; khi initiate operation ném `RuntimeException` ngay, code cũng chuyển thành lỗi để promise không treo.

Chương trình thử chờ `completion.get(5, TimeUnit.SECONDS)` trong main để **đảm bảo ghi xong mới đọc**. Trong server không muốn chặn request thread, caller có thể dùng các phương thức `CompletableFuture.thenApply`/`thenCompose` hoặc send message khi completion tới. Việc adapter trả `CompletableFuture` **không biến chữ ký overload channel thành CompletableFuture**.

## 9. Thread pool và thứ tự completion

Java SE 21 `AsynchronousFileChannel` nêu rõ:

- Channel được gắn với pool phục vụ I/O và dispatch handler.
- Handler chạy trên một thread trong pool gắn với channel.
- Nếu operation hoàn tất ngay và thread khởi tạo cũng là thread của pool, callback có thể chạy trực tiếp từ thread đó.
- Nhiều read/write có thể pending trên một channel.
- **Không bảo đảm thứ tự I/O và thứ tự callback đúng thứ tự submit**.
- ByteBuffers dùng cho concurrent I/O **không an toàn**; không truy cập buffer khi request còn pending.

**Phản ví dụ:**

~~~java
ByteBuffer shared = ByteBuffer.allocate(1024);
Future<Integer> a = channel.read(shared, 0L);
Future<Integer> b = channel.read(shared, 4096L);
~~~

Đây là code **không nên dùng**: hai outstanding operations cùng một ByteBuffer. Dù channel thread-safe, buffer không vì thế trở thành thread-safe.

Một handler xử lý lâu hoặc gọi `Future.get()` có thể giữ thread pool và gây nghẽn các handler khác. Nên xử lý completion ngắn, rồi chuyển việc nặng sang executor có giới hạn/backpressure. Nếu nhiều threads cùng thay state chung, đồng bộ thích hợp hoặc để mỗi request có attachment/state riêng.

### 9.1. Vị trí ghi giao nhau

Nếu hai writes vào cùng một vùng bytes đang pending đồng thời, kết quả cuối có thể phụ thuộc scheduling; không có cam kết operation khởi tạo trước sẽ hoàn thành trước. Thiết kế ghi tuần tự hoặc chia vùng offset **không chồng lấp**, rồi tổng hợp kết quả sau khi từng vùng hoàn tất.

### 9.2. Bảo vệ tài nguyên

Một ứng dụng có thể tạo quá nhiều Futures/buffers cùng lúc, làm tăng bộ nhớ và outstanding I/O. Giới hạn số requests pending và memory budget. Dùng executor riêng thì quản lý pool/handler shutdown; không gọi `shutdownNow` tùy ý khi còn dữ liệu cần ghi. Việc I/O bất đồng bộ có thể giúp tách công việc khỏi caller, **không đảm bảo throughput luôn cao hơn FileChannel tuần tự** trên mọi filesystem.

## 10. Timeout, cancellation, đóng channel

### 10.1. Timeout không phải cancel

`future.get(5, SECONDS)` quá hạn ném `TimeoutException` nhưng I/O vẫn **có thể đang pending**. Đừng lập tức reuse buffer hoặc close/retry theo offset cũ nếu chưa có chính sách xác minh trạng thái. Một write có thể đã ghi một phần dù caller chờ thất bại.

### 10.2. `Future.cancel(true)` không bảo đảm rollback

Javadoc `AsynchronousChannel` cảnh báo:

- Hủy Future khiến `get()` có thể ném `CancellationException`.
- Có hủy được I/O thực hay không **phụ thuộc implementation**.
- `cancel(true)` **có thể đóng channel** để ngắt; các I/O khác đang pending có thể thất bại với `AsynchronousCloseException`.
- Nếu implementation không thể bảo đảm một thao tác bị hủy chưa tác động bytes, channel có thể đi vào trạng thái lỗi không cho các thao tác tương tự.
- Buffer liên quan operation bị hủy cần được xử lý thận trọng, không tái dùng khi còn nguy cơ I/O tiếp tục truy cập.

Không dùng cancellation như transaction rollback hoặc làm bằng chứng “chưa ghi byte nào”.

### 10.3. `close()` khi request còn pending

`channel.close()` có thể được gọi khi có I/O outstanding, và contract khiến những operations đó thất bại với `AsynchronousCloseException`. Một operation mới trên channel đã đóng không thể tiếp tục bình thường.

**Phản ví dụ:**

~~~java
Future<Integer> pending;
try (AsynchronousFileChannel channel =
        AsynchronousFileChannel.open(file, StandardOpenOption.READ)) {
    pending = channel.read(buffer, 0L);
}
int n = pending.get(); // Channel đã đóng trước khi bảo đảm read xong.
~~~

Không dùng kiểu này trong luồng thực tế. Giữ channel mở đến khi operations cần thiết có kết quả, rồi đóng. `isOpen()` chỉ là quan sát, không thay thế xử lý race nếu thread khác đang đóng channel.

### 10.4. `force(boolean)` và durability

`AsynchronousFileChannel.force(boolean metaData)` yêu cầu đẩy cập nhật xuống thiết bị lưu trữ theo khả năng filesystem và contract, nhưng **không trả Future**. Đừng nhầm `Future<Integer>.get()` thành bảo đảm file đã fsync/crash-safe. Khi dữ liệu quan trọng, cần thiết kế thời điểm gọi `force` và quy trình lưu trữ/recovery phù hợp.

## 11. Khi nào nên dùng Future, khi nào dùng CompletionHandler?

| Tình huống | Hướng phù hợp |
| --- | --- |
| Muốn submit I/O, làm việc độc lập một lúc rồi đợi kết quả | `Future<Integer>` |
| Muốn timeout tiêu chuẩn khi chờ một operation | `Future.get(timeout, unit)`, nhưng nhớ I/O chưa chắc đã hủy |
| Muốn callback xử lý ngay khi I/O hoàn tất | `CompletionHandler` |
| Cần đính kèm ID/file offset/buffer cho từng request | `CompletionHandler` với attachment |
| Muốn composition dạng `thenCompose` | Tạo `CompletableFuture` adapter từ handler |
| Có nhiều I/O độc lập cần xử lý theo thứ tự nghiệp vụ | Mỗi buffer riêng, điều phối dependency và trạng thái |
| Cần read/write đầy đủ một logical buffer | Lặp Future theo completion hoặc callback chain theo count |
| Cần API phản hồi lỗi rõ ràng | Future qua `ExecutionException`; handler qua `failed` |
| File quá lớn, nhiều operation cùng lúc | Giới hạn concurrency, buffer budget, offset tường minh |
| File có thể thay đổi đồng thời | Version/locking/snapshot ngoài I/O result khi cần |

**Lựa chọn không phải “cái nào nhanh hơn chắc chắn”.** `Future` tiện cho code có thể chờ/điều phối, `CompletionHandler` tiện cho pipeline xử lý theo sự kiện. Tối ưu thực phụ thuộc provider, thiết bị, số operations, pool, buffer và xử lý phía ứng dụng.

## 12. EOF, partial I/O và filesystem đang thay đổi

### 12.1. EOF

Read trả `-1` nếu vị trí đọc **lớn hơn hoặc bằng size file tại thời điểm thực hiện read**. Nếu có actor khác append/truncate cùng file, EOF ở một thời điểm không đồng nghĩa file sẽ không bao giờ có dữ liệu tại offset đó.

### 12.2. Partial read/write

Một lần read thành công có thể đọc ít bytes hơn `buffer.remaining()` ban đầu. Tương tự write. Muốn truyền đầy đủ N bytes, phải quản lý offset, số lượng và buffer cho nhiều operations nối tiếp.

Không dùng vòng lặp retry vô hạn khi count 0. Trong sản phẩm, xác định deadline tổng và backoff phù hợp; ví dụ cố tình fail-fast cho Future, callback cho phép tối đa vài completions bằng 0 rồi báo lỗi.

### 12.3. Unicode và kích thước file

`String.length()` đếm UTF-16 code units, không phải bytes ghi qua UTF-8. Với tiếng Việt, ký tự có dấu có thể chiếm nhiều bytes. Nếu muốn đọc đủ nội dung UTF-8, phải xác định byte length tương ứng, không dùng độ dài chuỗi Java như file byte length.

### 12.4. Thay file và dữ liệu đang đọc

File có thể bị cắt, thay hoặc ghi đồng thời. Một read nhiều lượt có thể thấy nhiều trạng thái file khác nhau. `Future` hoàn tất chỉ bảo đảm operation cụ thể báo kết quả, **không tạo snapshot giao dịch**. Nếu yêu cầu dữ liệu nhất quán, cần thêm version, file identity, locking/snapshot phù hợp provider.

## 13. Lỗi thường gặp

| Sai lầm | Điều sai | Cách đúng |
| --- | --- | --- |
| Gọi `get()` ngay và tưởng không chặn caller | `get()` đợi completion | Dời thời điểm đợi hoặc dùng handler |
| Handler overload được giả định trả Future | Nó trả `void` | Xử lý trong callback hoặc adapter tự tạo |
| Cast Future của channel thành CompletableFuture | API không hứa như vậy | Tạo promise riêng |
| Coi `completed(n)` nghĩa đã truyền hết buffer | I/O có thể partial | Kiểm tra `hasRemaining()` |
| Coi 0 là EOF | EOF read là `-1` | Có no-progress policy |
| Đọc/ghi buffer khi operation pending | Có thể gây race | Đợi completion trước reuse |
| Chia sẻ một buffer cho hai requests pending | Buffer không safe | Một buffer/request |
| `flip` ngay sau khi gọi read | Chỉnh buffer lúc I/O chưa xong | Chỉ flip sau completion |
| Quên tăng file offset theo count | Dữ liệu lặp/ghi đè | `offset += count` |
| Coi hai callback đúng thứ tự submit | Không bảo đảm | Điều phối thứ tự nghiệp vụ |
| Callback chặn lâu | Nghẽn pool | Callback ngắn, offload |
| Không xử lý `failed` | Outcome bị mất | Propagate lỗi và cleanup |
| Timeout rồi reuse buffer | I/O có thể còn chạy | Quản lý completion/cancellation |
| Dùng `cancel(true)` như rollback | I/O có thể đã tác động bytes | Không bảo đảm atomicity |
| Đóng channel trước Future/handler xong | Pending operation thất bại | Giữ channel đủ lâu |
| Coi Future write thành công là fsync | Không phải durability contract | Xem `force`/OS policy |
| Ghi ở offset `size()` để append đồng thời | Không atomic | Serialize/append có contract riêng |
| Cho rằng mọi filesystem hỗ trợ I/O async như nhau | Provider có khác biệt | Bắt lỗi và test OS/provider đích |
| Tự động mở `CREATE`/`TRUNCATE_EXISTING` trên file user | Dễ xóa nội dung cũ | Dùng CREATE_NEW hoặc policy rõ |

## 14. Bài tập có đáp án

**Câu 1.** `channel.read(buffer, 0L)` trả về kiểu nào?

**Đáp án:** `Future<Integer>`. `get()` cho số bytes đọc được, hoặc `-1` khi EOF.

**Câu 2.** `channel.read(buffer, 0L, attachment, handler)` trả `Future` không?

**Đáp án:** Không. Nó trả `void`; outcome chuyển vào `completed` hoặc `failed`.

**Câu 3.** Một Future write đã hoàn tất với count 4 nhưng buffer ban đầu có 10 bytes. Có thể kết luận đã ghi 10 bytes chưa?

**Đáp án:** Chưa. Còn 6 bytes; nếu cần ghi đủ, tiếp tục tại file offset ban đầu cộng 4, sau khi operation trước hoàn tất.

**Câu 4.** `Future.get()` có thể chặn không?

**Đáp án:** Có. API khởi tạo asynchronous nhưng `get()` chờ completion.

**Câu 5.** `get(5, TimeUnit.SECONDS)` ném `TimeoutException` có phải I/O đã hủy?

**Đáp án:** Không. Nó chỉ hạn chế thời gian đợi của caller.

**Câu 6.** Khi đọc, `count == -1` nghĩa gì?

**Đáp án:** EOF ở vị trí đọc tại thời điểm thao tác đó được thực hiện; không phải `IOException`.

**Câu 7.** Vì sao không reuse một ByteBuffer cho hai read operations pending?

**Đáp án:** Contract không bảo đảm buffer an toàn khi concurrent I/O và không được truy cập buffer trước completion.

**Câu 8.** Attachment có vai trò gì?

**Đáp án:** Chứa ngữ cảnh riêng của request, ví dụ ID, offset, buffer và promise, để handler dùng chung vẫn phân biệt từng operation.

**Câu 9.** Có bảo đảm callback của hai read/write chạy đúng thứ tự khởi tạo?

**Đáp án:** Không. Phải điều phối nếu có dependency.

**Câu 10.** Nếu cancel Future với `true`, file chắc chắn chưa bị ghi bytes nào?

**Đáp án:** Không. Việc cancel underlying I/O là implementation-specific; channel có thể đóng hoặc lỗi, bytes đã ghi không tự rollback.

**Câu 11.** `AsynchronousFileChannel.force(true)` có trả Future không?

**Đáp án:** Không. `force` là operation đồng bộ có contract riêng; không lẫn với kết quả read/write.

**Câu 12.** Trong demo vì sao file cuối có size 15?

**Đáp án:** `"Future"` 6 byte UTF-8 cộng `"|Callback"` 9 byte = 15. Không phải vì một callback nào bắt buộc chạy 9 lần.

**Câu 13.** Muốn dùng `thenCompose` với callback I/O thì làm cách nào?

**Đáp án:** Tạo `CompletableFuture` adapter của ứng dụng, hoàn tất bằng `complete` hoặc `completeExceptionally` trong handler. Không cast Future của channel.

**Câu 14.** Vì sao phải giữ channel mở khi còn I/O pending?

**Đáp án:** Close có thể làm các outstanding operations thất bại với `AsynchronousCloseException`; buffer/result chưa được đảm bảo an toàn nếu caller bỏ mặc.

**Câu 15.** Gọi `channel.write(buffer, channel.size())` có atomic append không?

**Đáp án:** Không. Hai writers có thể cùng đọc size rồi ghi đè vùng nhau. Cần cơ chế serialize hoặc API append có contract phù hợp.

## 15. Checklist trước khi dùng trong ứng dụng thật

- [ ] Chọn đúng overload Future hoặc CompletionHandler; không đoán kiểu trả về.
- [ ] Mỗi operation truyền `filePosition >= 0`; channel không có current position chung.
- [ ] Đảm bảo channel có `READ`/`WRITE` và open options không vô tình xóa file.
- [ ] Mỗi pending I/O sở hữu buffer riêng; không chạm buffer tới khi completion.
- [ ] Xử lý partial I/O, `-1` EOF, count 0 không tiến triển.
- [ ] Dùng `flip()` đúng thời điểm trước khi decode read buffer.
- [ ] Nếu dùng Future, hiểu `get` có thể block và timeout không hủy operation.
- [ ] Bắt `InterruptedException`/`ExecutionException`/`TimeoutException`/`CancellationException`.
- [ ] Nếu dùng handler, viết cả `completed` và `failed`, attachment rõ ràng.
- [ ] Không dựa vào thứ tự completion của operations độc lập.
- [ ] Không chặn lâu trong completion pool; có executor riêng/backpressure khi cần.
- [ ] Không cast Future mặc định sang CompletableFuture.
- [ ] Giữ channel mở tới khi đã xử lý các operations quan trọng.
- [ ] Cẩn trọng khi cancel/close outstanding operations, nhất là buffer và dữ liệu có thể đã thay đổi.
- [ ] Đừng coi completed bytes là bảo đảm durability; cân nhắc `force`.
- [ ] Test trên provider đích; file thay đổi đồng thời có thể yêu cầu snapshot/locking.
- [ ] Chỉ dùng NIO.2 và các API vẫn được hỗ trợ trên JDK hiện đại, đúng Special Note.

## 16. Tài liệu chính thức

- [Java SE 21 — AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): `read`/`write` dạng Future hoặc CompletionHandler, file positions, pool, buffer safety, close/force/size.
- [Java SE 21 — AsynchronousChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousChannel.html): cancellation, `AsynchronousCloseException`, hai mô hình I/O.
- [Java SE 21 — CompletionHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/CompletionHandler.html): hai callback `completed` và `failed`, generic `V,A`.
- [Java SE 21 — Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): `get`, `isDone`, `isCancelled` và `cancel`.
- [Java SE 21 — CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): adapter callback/composition do ứng dụng tự tạo.
- [Java SE 21 — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): position/limit/remaining/flip/wrap/allocate.
- [Java SE 21 — StandardOpenOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardOpenOption.html): READ/WRITE/CREATE_NEW và options mở file.

**Kết luận:** `AsynchronousFileChannel` cung cấp hai cách tiêu thụ kết quả cùng một loại I/O: **Future** để kiểm tra/chờ kết quả khi caller quyết định, và **CompletionHandler** để nhận callback có attachment. Chọn cách nào cũng phải quản lý **offset, ByteBuffer, số bytes thực truyền, EOF, lỗi, cancellation và vòng đời channel**. Asynchronous API chỉ tạo khả năng phối hợp tốt hơn; độ đúng và hiệu năng vẫn phụ thuộc cách bạn điều phối request, provider và giới hạn tài nguyên.
