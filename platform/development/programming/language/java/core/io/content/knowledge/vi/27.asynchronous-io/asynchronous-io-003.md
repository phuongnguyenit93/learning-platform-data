# Future và CompletionHandler trong Java NIO.2: Hai cách nhận kết quả I/O bất đồng bộ

## 1. Bài toán và mục tiêu

Với I/O đồng bộ quen thuộc, lệnh `channel.read(buffer)` thường chỉ trả về khi thao tác đọc đã có kết quả. Java NIO.2 cung cấp các kênh bất đồng bộ trong gói `java.nio.channels`, cho phép **khởi phát thao tác I/O rồi nhận kết quả về sau**.

Các lớp tiêu biểu gồm:

- `AsynchronousFileChannel`: đọc/ghi vùng tệp tại offset cụ thể.
- `AsynchronousSocketChannel`: kết nối, đọc và ghi qua TCP theo mô hình bất đồng bộ.
- `AsynchronousServerSocketChannel`: nhận kết nối TCP theo mô hình bất đồng bộ.

Hai kiểu API chủ đạo là **`Future`** và **`CompletionHandler`**:

1. **`Future`:** phương thức I/O trả về một đối tượng đại diện kết quả chưa hoàn tất; ứng dụng kiểm tra trạng thái hoặc gọi `get()` để đợi và lấy kết quả.
2. **`CompletionHandler`:** khi gọi I/O, ứng dụng truyền callback; khi thao tác kết thúc, hệ thống gọi `completed(...)` hoặc `failed(...)`.

**Bất đồng bộ không có nghĩa dữ liệu chắc chắn đã sẵn ngay**, thao tác luôn chạy trên một luồng mới, hay mỗi lần đọc/ghi sẽ chuyển đủ số byte yêu cầu. Phần quan trọng là biết khi nào công việc hoàn thành, kết quả thực tế là bao nhiêu và ai quản lý vòng đời buffer/channel.

Sau bài này, bạn sẽ hiểu cách chọn `Future` hoặc `CompletionHandler`, xử lý đọc/ghi một phần, lỗi, timeout, hủy thao tác và viết ví dụ Java 17+ có thể chạy độc lập.

## 2. So sánh chữ ký API

### 2.1. `AsynchronousFileChannel`

Hai phương thức cùng thực hiện đọc ở một offset rõ ràng nhưng sử dụng mô hình trả kết quả khác nhau:

~~~java
// Future: kết quả được lấy từ đối tượng Future<Integer>.
Future<Integer> read(ByteBuffer dst, long position);

// Callback: hệ thống chuyển kết quả tới CompletionHandler.
<A> void read(
        ByteBuffer dst,
        long position,
        A attachment,
        CompletionHandler<Integer, ? super A> handler);
~~~

Tương tự cho thao tác ghi:

~~~java
Future<Integer> write(ByteBuffer src, long position);

<A> void write(
        ByteBuffer src,
        long position,
        A attachment,
        CompletionHandler<Integer, ? super A> handler);
~~~

Đây là **chữ ký phương thức được giản lược để học**, không phải chương trình Java độc lập. `position` là offset tính theo **byte trong tệp**, không phải `ByteBuffer.position()` và không phải vị trí con trỏ tệp chia sẻ.

Với `AsynchronousFileChannel`, không có ý tưởng “file position hiện tại” để dựa vào như `FileChannel.position()`: mỗi lệnh đọc/ghi dùng offset tường minh. Khi thao tác trả về `n` byte, lần tiếp theo xử lý phần còn lại tại `position + n`.

### 2.2. `AsynchronousSocketChannel`

~~~java
Future<Void> connect(SocketAddress remote);
<A> void connect(
        SocketAddress remote,
        A attachment,
        CompletionHandler<Void, ? super A> handler);

Future<Integer> read(ByteBuffer dst);
<A> void read(
        ByteBuffer dst, A attachment,
        CompletionHandler<Integer, ? super A> handler);

Future<Integer> write(ByteBuffer src);
<A> void write(
        ByteBuffer src, A attachment,
        CompletionHandler<Integer, ? super A> handler);
~~~

Đây cũng là **chữ ký minh họa**; một số API có thêm các overload cho timeout hoặc nhiều buffer. Khác với file channel, socket không có offset tệp; byte được nhận/gửi nối tiếp trên luồng TCP.

| Đặc điểm | `Future` | `CompletionHandler` |
| --- | --- | --- |
| Nhận kết quả | Gọi `future.get()` hoặc kiểm tra `isDone()` | Callback `completed(result, attachment)` |
| Lỗi I/O trong quá trình thực thi | Thường được gói trong `ExecutionException` khi gọi `get()` | Callback `failed(exc, attachment)` |
| Chờ hoàn tất | `get()` **chặn luồng gọi**; có biến thể timeout | Không cần chặn luồng khởi phát chỉ để đợi kết quả |
| Phối hợp nhiều bước | Dễ viết tuần tự, nhưng phải quản lý việc chờ | Có thể nối bước từ callback, hoặc chuyển sang `CompletableFuture` |
| Nguy cơ thường gặp | Gọi `get()` ngay rồi vô tình chặn luồng quan trọng | Callback dài, lỗi không được chuyển ra nơi quan sát, hoặc rối luồng điều khiển |
| Hủy | `Future.cancel(...)` cung cấp giao diện yêu cầu hủy | Không có đối tượng `Future` do overload callback trả về |
| Gắn ngữ cảnh | Tự giữ trạng thái bên ngoài `Future` | Dùng `attachment` để chuyển trạng thái tới callback |

Một phương thức chọn overload `Future` **không đồng thời** gọi `CompletionHandler` của overload khác. Hai kiểu thể hiện cùng ý tưởng kết quả bất đồng bộ, nhưng cách tiếp nhận và phối hợp hoàn thành khác nhau.

## 3. Dòng thời gian của một thao tác bất đồng bộ

Với `Future`:

~~~text
Luồng gọi:
  tạo ByteBuffer
       |
  Future<Integer> f = channel.read(buffer, offset)
       |
  xử lý tác vụ độc lập khác (nếu có)
       |
  f.get()  -- có thể phải đợi -->
       |
  đọc số byte thực tế; xử lý buffer/EOF/lỗi
~~~

Với `CompletionHandler`:

~~~text
Luồng khởi phát:
  channel.read(buffer, offset, state, handler)
       |
  tiếp tục chạy công việc khác

Khi I/O kết thúc:
  handler.completed(n, state)
       hoặc
  handler.failed(error, state)
~~~

**Điểm rất dễ nhầm:** `channel.read(...)` trả về `Future` nhanh không có nghĩa lệnh đọc đã hoàn thành. Ngược lại, việc callback chạy sau đó không có nghĩa nó luôn chạy trên một thread dành riêng cho yêu cầu; chính sách thực thi phụ thuộc provider và nhóm luồng/channel.

## 4. Cách dùng `Future` đúng

### 4.1. Khởi phát rồi nhận kết quả

~~~java
ByteBuffer buffer = ByteBuffer.allocate(1024);
Future<Integer> pending = file.read(buffer, 0L);

// Có thể làm một công việc khác tại đây.
int n = pending.get(); // Chặn luồng gọi nếu I/O chưa xong.
~~~

Đoạn mã dùng một `AsynchronousFileChannel file` đã mở và cần import `ByteBuffer`, `Future`. `get()` có thể ném `InterruptedException` hoặc `ExecutionException`; ví dụ này chỉ minh họa luồng thao tác.

Các phương thức quan trọng:

- `future.isDone()`: cho biết thao tác đã đi đến trạng thái kết thúc (thành công, thất bại hoặc đã hủy), **không có nghĩa chắc chắn thành công**.
- `future.get()`: đợi rồi nhận kết quả; lỗi thực thi được bọc trong `ExecutionException`.
- `future.get(timeout, unit)`: giới hạn **thời gian chờ của luồng gọi**; có thể ném `TimeoutException`.
- `future.cancel(mayInterruptIfRunning)`: yêu cầu hủy; có thể trả `false` nếu không hủy được. Sau khi hủy, `get()` có thể ném `CancellationException`.
- `future.isCancelled()`: kiểm tra trạng thái hủy của Future.

**Timeout khi đợi không nhất thiết dừng I/O.** Sau `get(2, SECONDS)` bị `TimeoutException`, thao tác đọc/ghi có thể vẫn đang chạy. Ứng dụng phải quyết định tiếp tục chờ, yêu cầu hủy hoặc đóng tài nguyên; không nên tái sử dụng `ByteBuffer` như thể I/O đã kết thúc.

### 4.2. Phân biệt lỗi lúc khởi phát và lỗi khi thực thi

Một số lỗi có thể xảy ra **ngay ở lời gọi `read/write`**, chẳng hạn tham số không hợp lệ hoặc channel đã đóng. Những lỗi khác phát sinh sau khi thao tác bắt đầu:

~~~java
try {
    Future<Integer> f = file.read(buffer, offset);
    int n = f.get();
    // Xử lý n: n>0, n==0 hoặc n==-1 (đối với đọc).
} catch (ExecutionException ex) {
    Throwable actualCause = ex.getCause();
    // Ghi log/ánh xạ lỗi từ tác vụ I/O.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Tôn trọng chính sách hủy tác vụ của luồng gọi.
}
~~~

Đây là đoạn minh họa với `file`, `buffer`, `offset` đã khai báo và import `Future`, `ExecutionException`. Phải xử lý thêm các lỗi hợp lệ của phương thức khi dùng trong chương trình thật.

**Đừng nuốt `InterruptedException`:** nên phục hồi cờ interrupt bằng `Thread.currentThread().interrupt()` hoặc truyền lỗi theo chính sách của ứng dụng. `get()` bị ngắt không tự chứng minh I/O đã bị hủy.

## 5. Cách dùng `CompletionHandler` đúng

Một `CompletionHandler<V,A>` có hai kiểu tham số:

- `V` là **loại kết quả** của một lần I/O, thường là `Integer` cho số byte đọc/ghi hoặc `Void` cho connect.
- `A` là **loại attachment** do người gọi tự chọn, để mang ngữ cảnh như request id, offset, buffer, trạng thái hoặc đối tượng theo dõi.

~~~java
channel.read(buffer, 0L, requestId,
    new CompletionHandler<Integer, String>() {
        @Override
        public void completed(Integer bytesRead, String id) {
            System.out.println(id + ": " + bytesRead);
        }

        @Override
        public void failed(Throwable error, String id) {
            System.err.println(id + ": " + error);
        }
    });
~~~

Đây là đoạn minh họa; `channel` là `AsynchronousFileChannel`, `buffer` là `ByteBuffer`, `requestId` là `String` và cần import `CompletionHandler`. Callback `completed` chỉ cho biết **một thao tác** đã hoàn tất; nếu `bytesRead` còn thiếu, bạn cần tự khởi phát lần đọc tiếp theo.

### 5.1. Callback nên làm gì?

Trong phương thức `completed`:

1. Kiểm tra số byte thực tế được đọc/ghi.
2. Cập nhật buffer và offset hoặc trạng thái giao thức.
3. Nếu còn dữ liệu cần xử lý, khởi phát thao tác tiếp theo.
4. Nếu hoàn tất toàn bộ yêu cầu, thông báo cho thành phần chờ hoặc phát kết quả.

Trong phương thức `failed`:

1. Ghi nhận nguyên nhân thực tế.
2. Đánh dấu tác vụ thất bại **một lần**.
3. Giải phóng/đóng tài nguyên theo chính sách ownership.

Đừng làm việc CPU nặng, sleep hoặc chờ khóa kéo dài trong callback nếu việc đó chiếm luồng dùng chung để hoàn tất các I/O khác. Nên chuyển công việc nặng sang executor thích hợp.

### 5.2. Attachment giúp tránh trộn trạng thái

Khi nhiều I/O cùng diễn ra, attachment cho phép mỗi callback biết mình thuộc thao tác nào:

~~~java
record RequestState(String id, long fileOffset) {}

RequestState state = new RequestState("req-42", 4096L);
channel.read(buffer, state.fileOffset(), state,
    new CompletionHandler<Integer, RequestState>() {
        @Override
        public void completed(Integer result, RequestState request) {
            System.out.println(request.id() + " -> " + result);
        }

        @Override
        public void failed(Throwable exc, RequestState request) {
            System.err.println(request.id() + ": " + exc);
        }
    });
~~~

Đây là đoạn minh họa cho Java 17+, với `channel`/`buffer` đã mở và import `CompletionHandler`. Khi xử lý tiếp byte còn lại, cần cập nhật offset dựa trên **số byte đã thực sự chuyển**, không dựa trên kích thước yêu cầu ban đầu.

Attachment không tự giải quyết tranh chấp thread hay chia sẻ buffer; trạng thái mutable vẫn cần ownership hoặc đồng bộ thích hợp.

## 6. Kết quả thực tế và vòng lặp đọc/ghi từng phần

Với `AsynchronousFileChannel.read(dst, position)`:

- `n > 0`: có `n` byte được đưa vào buffer; `ByteBuffer.position()` tăng theo `n`.
- `n == -1`: EOF, không còn byte ở vị trí đọc yêu cầu.
- `n == 0`: lần này không chuyển byte; có thể là buffer không còn chỗ hoặc tình huống không tiến triển. **Không coi `0` là đã đủ dữ liệu**.

Với `write(src, position)`:

- `n > 0`: đã ghi `n` byte, `src.position()` tăng tương ứng.
- `n == 0`: chưa chuyển byte nào; cần có chính sách retry/backoff hoặc báo lỗi cho workload phù hợp.
- Ghi không có giá trị `-1` để biểu thị EOF như thao tác đọc.

### 6.1. Mẫu `Future` viết đủ toàn bộ buffer

~~~java
long fileOffset = 0L;

while (src.hasRemaining()) {
    Future<Integer> f = file.write(src, fileOffset);
    int n = f.get();

    if (n <= 0) {
        throw new IOException("Không có tiến triển khi ghi");
    }

    fileOffset += n;
}
~~~

Đây là đoạn minh họa với `file` là `AsynchronousFileChannel` mở quyền ghi, `src` là `ByteBuffer` có dữ liệu sẵn; cần xử lý các checked exception `get()` theo ngữ cảnh. Chương trình mẫu đầy đủ ở phần sau thể hiện cách dùng này.

**Sai lầm nguy hiểm:** khởi phát nhiều `write` trên **cùng một ByteBuffer** trước khi thao tác trước hoàn tất rồi tự tăng offset từ số byte yêu cầu. Bộ đệm bị dùng đồng thời có thể làm dữ liệu/vị trí không xác định theo mong đợi. Với ví dụ tuần tự, chỉ thực hiện lần tiếp theo sau khi đã nhận kết quả của lần hiện tại.

### 6.2. Mẫu callback đọc đủ số byte mục tiêu

Ý tưởng:

~~~text
Đọc tại offset p vào buffer
  |
  +-- n > 0, buffer còn chỗ: đọc tiếp tại p + n
  |
  +-- n > 0, buffer đã đủ: báo thành công
  |
  +-- n == -1: báo EOF sớm nếu còn thiếu byte
  |
  +-- n == 0: xử lý chính sách không tiến triển
  |
  +-- failed(error): báo lỗi
~~~

Phải nhớ rằng `CompletionHandler.completed(n, attachment)` tương ứng **một lần đọc**, không tương ứng luôn cả message hay toàn bộ file.

## 7. Ví dụ Java 17+ hoàn chỉnh: Future để ghi, CompletionHandler để đọc

Chương trình chạy độc lập dưới đây tạo tệp tạm, dùng `Future<Integer>` để ghi đủ `HELLO` vào tệp, sau đó dùng `CompletionHandler` để đọc đủ 5 byte. Kết quả callback được nối với `CompletableFuture` để thread chính có thể đợi hoàn tất và in kết quả có thứ tự.

**Lưu mã thành `AsyncIoFutureHandlerDemo.java`:**

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
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class AsyncIoFutureHandlerDemo {

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("async-io-", ".txt");

        try {
            try (AsynchronousFileChannel channel =
                         AsynchronousFileChannel.open(
                                 file,
                                 StandardOpenOption.READ,
                                 StandardOpenOption.WRITE)) {

                ByteBuffer src = ByteBuffer.wrap(
                        "HELLO".getBytes(StandardCharsets.UTF_8));

                long offset = 0L;
                while (src.hasRemaining()) {
                    Future<Integer> pending = channel.write(src, offset);
                    int n = pending.get();

                    if (n <= 0) {
                        throw new IOException("Future write không tiến triển");
                    }
                    offset += n;
                }

                System.out.println("Future bytes written: " + offset);

                ByteBuffer dst = ByteBuffer.allocate(5);
                CompletableFuture<Integer> done = readFully(
                        channel, dst, 0L);

                int readBytes = done.get(5, TimeUnit.SECONDS);
                dst.flip();

                System.out.println("Handler bytes read: " + readBytes);
                System.out.println("Content: "
                        + StandardCharsets.UTF_8.decode(dst));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }

    private static CompletableFuture<Integer> readFully(
            AsynchronousFileChannel channel,
            ByteBuffer dst,
            long fileOffset) {

        CompletableFuture<Integer> done = new CompletableFuture<>();

        channel.read(dst, fileOffset, fileOffset,
                new CompletionHandler<Integer, Long>() {
                    private int total;

                    @Override
                    public void completed(Integer n, Long currentOffset) {
                        if (n == -1) {
                            done.completeExceptionally(
                                    new EOFException("Tệp kết thúc sớm"));
                            return;
                        }

                        if (n == 0) {
                            done.completeExceptionally(
                                    new IOException("Đọc không tiến triển"));
                            return;
                        }

                        total += n;
                        if (!dst.hasRemaining()) {
                            done.complete(total);
                            return;
                        }

                        long nextOffset = currentOffset + n;
                        try {
                            channel.read(
                                    dst, nextOffset, nextOffset, this);
                        } catch (RuntimeException ex) {
                            done.completeExceptionally(ex);
                        }
                    }

                    @Override
                    public void failed(Throwable error, Long ignoredOffset) {
                        done.completeExceptionally(error);
                    }
                });

        return done;
    }
}
~~~

Chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 AsyncIoFutureHandlerDemo.java
java AsyncIoFutureHandlerDemo
~~~

**Stdout kỳ vọng khi I/O hoàn tất bình thường:**

~~~text
Future bytes written: 5
Handler bytes read: 5
Content: HELLO
~~~

### Giải thích mã và tính đúng đắn

1. `Files.createTempFile` tạo tệp trống và sinh tên khác nhau mỗi lần. Vì stdout không in tên tệp nên kết quả hiển thị ổn định.
2. `AsynchronousFileChannel.open` mở channel với quyền đọc và ghi. Không có `position()` của file channel; mỗi lần gọi cung cấp offset tệp.
3. `Future<Integer> pending = channel.write(src, offset)` khởi phát một lần ghi. `pending.get()` đợi đến khi có số byte thực tế, sau đó `offset += n` để tiếp tục phần còn lại. `src.position()` cũng đã tăng theo số byte ghi.
4. `ByteBuffer.wrap(...)` cung cấp chính xác 5 byte UTF-8 của `HELLO`. Nếu mỗi lần chỉ ghi một phần, vòng lặp vẫn ghi hết trước khi bắt đầu đọc.
5. `readFully(...)` khởi phát lần đọc đầu tiên và trả về `CompletableFuture` biểu diễn **toàn bộ quá trình đọc**, gồm những lần đọc tiếp theo nếu một callback trả về ít byte hơn cần thiết.
6. Mỗi khi `completed(n, currentOffset)` nhận `n > 0`, buffer đã được cập nhật `position`, nên lần đọc tiếp theo dùng **chính buffer** nhưng với offset tệp `currentOffset + n`. Không tự tăng `dst.position()` lần thứ hai.
7. Khi đã đủ 5 byte, callback gọi `done.complete(total)`. Khi xảy ra EOF sớm, không có tiến triển hoặc lỗi I/O, callback dùng `completeExceptionally(...)`.
8. `done.get(5, SECONDS)` chỉ giúp thread chính đợi và áp dụng giới hạn thời gian chờ; callback làm việc trên hạ tầng xử lý I/O của channel. Timeout không tự chứng minh rằng thao tác đã bị hủy.
9. Sau khi hoàn tất, `dst.flip()` chuyển buffer sang trạng thái đọc để giải mã chính xác 5 byte. Chương trình dùng ASCII trong UTF-8 nên không có byte ký tự nhiều byte nằm dở.
10. `try-with-resources` đóng channel rồi `finally` xóa tệp tạm. Nếu có exception, chương trình không giả vờ thành công.

**Giới hạn có chủ đích của ví dụ:** nếu file ổn định và buffer còn chỗ nhưng thao tác đọc trả `0`, ví dụ báo lỗi để tránh vòng lặp không tiến triển. Một ứng dụng mạng hoặc nguồn thay đổi cần chính sách retry/readiness/timeout riêng. Khi timeout xảy ra, chương trình rời `try-with-resources` và đóng channel; cách dừng/cancel thực tế cần được thiết kế rõ trong hệ thống sản xuất.

## 8. `Future` không đồng nghĩa “ứng dụng hoàn toàn không chặn”

Khai báo:

~~~java
Future<Integer> f = channel.read(dst, 0);
int n = f.get();
~~~

là I/O được **khởi phát bất đồng bộ**, nhưng **luồng gọi trở thành chờ đồng bộ tại `get()`**. Nếu cứ gọi `get()` ngay sau mỗi thao tác, hiệu quả về tổ chức luồng có thể rất giống với cách đọc tuần tự.

`Future` vẫn hữu ích trong các trường hợp:

- Tạo I/O rồi xử lý công việc độc lập trước khi cần kết quả.
- Gửi nhiều thao tác **trên các buffer độc lập**, lưu các Future và đợi chúng sau đó.
- Chuyển Future sang một bộ phối hợp khác và để worker chuyên trách đợi kết quả.
- Dùng timeout ở ranh giới yêu cầu khi mô hình thread cho phép chờ.

**`isDone()` + polling liên tục** thường không tốt: tạo busy-spin và khó đặt timeout. Thay bằng `get(timeout, unit)` ở một thread có thể chờ, hoặc dùng callback để nhận tín hiệu khi hoàn thành.

## 9. `CompletionHandler` không tự tạo chuỗi Future và không tự giới hạn tải

Một callback có thể “nối tiếp” thao tác bằng cách gọi lại `read/write` trong `completed`. Tuy nhiên, nếu có hàng chục nghìn kết nối hoặc request, ứng dụng vẫn phải quản lý:

- **Số thao tác đang bay (in-flight):** giới hạn số request và tổng byte/buffer tồn tại đồng thời.
- **Ownership:** ai được đọc/sửa buffer khi thao tác chưa hoàn tất.
- **Thời hạn:** nếu peer không phản hồi, callback có thể chưa đến trong thời gian ứng dụng mong muốn; phải có timeout/hủy/đóng có kiểm soát.
- **Lỗi:** callback `failed` phải được đưa đến log, trạng thái request hoặc Future hoàn tất lỗi; ném exception ra khỏi callback không tương đương với ném từ dòng mã đã khởi phát.
- **Đóng tài nguyên:** channel có thể bị đóng khi còn thao tác chờ; callback/future phải xử lý kết thúc bất thường.
- **Thứ tự nghiệp vụ:** những callback của các thao tác độc lập có thể hoàn thành **không theo thứ tự bắt đầu**, ngay cả khi dữ liệu cần được công bố theo thứ tự.

**Không dùng một `ByteBuffer` mutable cho nhiều thao tác I/O đồng thời** nếu chưa có thiết kế đồng bộ đặc biệt. Thực tế, dùng buffer riêng cho từng request hoặc điều phối một chuỗi thao tác sao cho chỉ có một I/O thao tác trên buffer trong một thời điểm sẽ dễ kiểm tra hơn.

## 10. Khác biệt giữa file và socket bất đồng bộ

### 10.1. File: offset độc lập

`AsynchronousFileChannel.read(dst, position)` đọc theo offset byte được cung cấp. Hai lần đọc tại offset 0 và 4096 là hai yêu cầu khác nhau; chúng có thể hoàn tất theo thứ tự khác nhau và phải có buffer độc lập nếu chạy đồng thời.

Lưu ý rằng Java có thể triển khai I/O file bất đồng bộ bằng thread pool và thao tác hệ điều hành thông thường tùy nền tảng. **Không bảo đảm mỗi thao tác là kernel-native async/zero-copy**, cũng không bảo đảm tăng tốc trên mọi workload. Nếu mục tiêu là hiệu năng, phải đo throughput, CPU, context switches, concurrency và độ trễ.

### 10.2. Socket: byte stream và backpressure

`AsynchronousSocketChannel` dùng TCP byte stream. Một lần `read` có thể trả về ít hơn độ dài message; một lần `write` có thể gửi ít hơn số byte còn trong buffer. Cần **message framing** như length-prefix hoặc delimiter nếu giao thức yêu cầu bản tin.

Một số lỗi đặc trưng cần ghi nhớ:

- `ReadPendingException`: cố khởi phát thao tác đọc khác khi socket đang có một thao tác đọc chưa hoàn tất.
- `WritePendingException`: tương tự cho chiều ghi.
- `NotYetConnectedException`: đọc/ghi trước khi kết nối đã được thiết lập.
- `AsynchronousCloseException`/`ClosedChannelException`: đóng channel có thể ảnh hưởng thao tác đang chờ.

Vì vậy, với socket thường xây dựng một **read loop** tiếp nối sau mỗi kết quả nhận và một **write queue** gửi lần lượt các buffer; không bắn nhiều lần `read` song song trên cùng `AsynchronousSocketChannel` rồi hy vọng chúng tự xếp thứ tự.

`Future<Void> connect(...)` cho kết quả kiểu `Void`; khi kết nối thành công thì `get()` trả `null`. Với callback connect, `completed(null, attachment)` chỉ báo thao tác kết nối hoàn thành, không tự bảo đảm server đã xử lý request.

## 11. Executor, thread pool và sự an toàn của callback

Java NIO.2 dùng nhóm luồng (asynchronous channel group) hoặc executor theo API và loại channel. Chẳng hạn:

- `AsynchronousFileChannel.open(path, options, executor, attrs...)` có overload cho `ExecutorService`.
- `AsynchronousChannelGroup.withFixedThreadPool(...)` có thể cung cấp group cho các socket/server channel bất đồng bộ.

**Không gắn một executor riêng cho từng thao tác nhỏ**: dễ gây bùng nổ số thread, tốn bộ nhớ và chi phí chuyển ngữ cảnh. Hãy thiết kế executor/group theo vòng đời ứng dụng hoặc service.

Nếu callback chia sẻ biến đếm/trạng thái giữa các thread, cần bảo đảm an toàn bộ nhớ bằng ownership, `AtomicInteger`, đồng bộ, immutable data hoặc cơ chế điều phối phù hợp. `CompletableFuture.complete(...)` cung cấp điểm công bố kết quả thuận tiện; nhưng các đối tượng mutable như `ByteBuffer` vẫn cần quy tắc chỉ sử dụng sau khi I/O hoàn tất.

### Một lưu ý về deadlock và starvation

Đừng gọi `future.get()` bên trong callback nếu Future đó chỉ có thể hoàn thành khi một tác vụ khác chạy trên cùng một executor đã bị bạn chặn hết worker. Điều này có thể dẫn đến starvation/deadlock.

Cũng đừng chạy phân tích dữ liệu nặng nhiều giây trong callback của executor I/O dùng chung. Hãy chuyển phần xử lý CPU lớn sang executor tính toán nếu cần.

## 12. Timeout, cancellation và lifecycle

### 12.1. Timeout của người đợi

~~~java
try {
    int n = future.get(3, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    // Quyết định retry, cancel hoặc đóng channel theo hợp đồng.
}
~~~

Đoạn minh họa dùng `Future<Integer> future` đã có và import `TimeoutException`, `TimeUnit`. **Timeout ở `get` là timeout chờ kết quả**, không bảo đảm I/O đã dừng ngay.

Một số overload của API socket còn cho phép cấu hình timeout trực tiếp khi thực hiện `read/write` bất đồng bộ; cần xem hợp đồng API riêng của overload đó, thay vì áp dụng logic timeout của `Future.get` cho mọi channel.

### 12.2. Cancellation không đồng nghĩa rollback

Nếu gọi:

~~~java
boolean cancelled = future.cancel(true);
~~~

việc hủy thành công Future **không có nghĩa các byte đã ghi trước đó được hoàn tác**. Thao tác I/O có thể đã chuyển một phần trước khi hủy hoặc channel có thể phải đóng tùy trường hợp/triển khai.

Tránh đọc hoặc tái sử dụng buffer ngay sau yêu cầu cancel nếu chưa chắc tác vụ trước đã chấm dứt quyền truy cập. Các lựa chọn an toàn thường là đợi xác nhận hoàn tất, tổ chức ownership nghiêm ngặt hoặc đóng và bỏ channel/buffer theo chính sách quản lý tài nguyên.

### 12.3. Đóng channel

Một channel có thể đóng khi các I/O còn chờ; những yêu cầu đó có thể thất bại. Với chương trình xử lý nhiều request, phải bảo đảm **mọi request có trạng thái kết thúc**: thành công, lỗi, hủy hoặc timeout. Đừng để callback lỗi mất tín hiệu và caller đợi mãi.

`try-with-resources` hợp lý khi vòng đời I/O được quản lý trong một block; tuy nhiên với callback, **không đóng channel ngay sau khi đăng ký callback** nếu còn cần nó cho việc hoàn tất. Phải giữ channel sống đến khi các thao tác cần thiết hoàn tất hoặc bị hủy có kiểm soát.

## 13. Các lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Gọi `Future.get()` ngay trên event-loop/UI thread | Chặn luồng quan trọng | Đưa việc đợi sang worker thích hợp hoặc dùng callback |
| Nghĩ `future.isDone() == true` tức thành công | Bỏ sót lỗi/hủy | Dùng `get()` hoặc kiểm tra trạng thái và xử lý exception |
| Bỏ qua `ExecutionException.getCause()` | Không thấy nguyên nhân I/O | Ghi và phân loại nguyên nhân gốc |
| Nuốt `InterruptedException` | Mất tín hiệu dừng | Phục hồi interrupt hoặc truyền theo chính sách |
| Giả định một lần `read/write` chuyển đủ byte | Mất dữ liệu hoặc ghi thiếu | Dùng kết quả thực tế để tiếp tục |
| Đọc buffer trước khi I/O hoàn tất | Dữ liệu/chỉ số chưa ổn định | Giữ ownership cho thao tác đang chạy |
| Một buffer cho nhiều I/O song song | Tranh chấp `position/limit` | Dùng buffer riêng hoặc xếp hàng |
| Quên `failed(...)` | Request chờ mãi | Kết thúc request bằng trạng thái lỗi |
| Đóng channel ngay sau `read(..., handler)` | I/O đang chạy thất bại | Giữ channel sống qua vòng đời thao tác |
| Làm CPU-bound/blocking việc dài trong callback | Giảm khả năng xử lý I/O khác | Chuyển việc sang executor phù hợp |
| Retry liên tục khi `n == 0` | Busy-spin, phí CPU | Chờ điều kiện thích hợp hoặc fail fast có chủ đích |
| Nhầm `get(timeout)` với hủy I/O | Tác vụ vẫn đang dùng buffer | Hủy/đóng/quản lý vòng đời riêng |
| Gọi 2 lần `read` đồng thời trên cùng async socket | `ReadPendingException` | Xây read loop tuần tự |
| Phụ thuộc callback hoàn thành đúng thứ tự gửi | Lỗi sắp xếp nghiệp vụ | Gắn request id và điều phối thứ tự |

## 14. Chọn `Future` hay `CompletionHandler`?

**Chọn `Future`** khi bạn muốn viết luồng điều khiển dễ đọc, có worker được phép đợi hoặc cần áp dụng timeout cho việc chờ. Ví dụ batch job xử lý một số tệp độc lập: khởi phát nhiều thao tác trên các buffer riêng, làm việc khác, rồi lấy kết quả khi cần.

**Chọn `CompletionHandler`** khi cần nhiều I/O đồng thời và muốn hệ thống thông báo ngay khi một thao tác hoàn thành, phù hợp với pipeline, socket server hoặc chuỗi tác vụ theo sự kiện. Phải quản lý trạng thái callback và giới hạn tải.

**Kết hợp `CompletionHandler` với `CompletableFuture`** là cách hữu ích để chuyển callback thành một biểu diễn kết quả có thể phối hợp. Ví dụ ở trên cho thấy một `CompletableFuture` đại diện **cả quá trình đọc đầy đủ**, dù các thao tác nền diễn ra qua nhiều callback.

Lựa chọn còn phụ thuộc thư viện, cấu trúc executor, số kết nối/tệp đồng thời, yêu cầu độ trễ, xử lý lỗi và mức độ dễ kiểm thử. **Hai API không tự làm cho I/O nhanh hơn chỉ bởi kiểu thông báo kết quả**.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `Future<Integer> f = channel.read(buffer, 0)` vừa trả về. Dữ liệu trong `buffer` đã sẵn để xử lý chưa?

**Đáp án:** Không thể kết luận. Phải đợi/kiểm tra thao tác hoàn tất, xử lý kết quả rồi mới dùng buffer.

**Câu 2.** `f.get()` ném `ExecutionException`. I/O thành công hay thất bại?

**Đáp án:** Thao tác đã thất bại; xem `getCause()` để biết nguyên nhân. `Future.isDone()` vẫn có thể trả `true`.

**Câu 3.** Một lời gọi bất đồng bộ ghi 10 byte nhưng callback nhận `completed(4, attachment)`. Có thể coi đã ghi đủ chưa?

**Đáp án:** Chưa. Đã chuyển 4 byte; phải giữ 6 byte còn lại và tiếp tục theo vị trí/buffer thực tế.

**Câu 4.** Đọc qua `AsynchronousFileChannel` trả `-1` khi buffer đang cần 5 byte nữa. Ý nghĩa gì?

**Đáp án:** EOF trước khi đủ dữ liệu dự kiến. Nếu giao thức/yêu cầu đòi đúng 5 byte còn thiếu, đây là lỗi dữ liệu không đầy đủ.

**Câu 5.** Gọi `get(1, SECONDS)` bị `TimeoutException`. Có được sửa ngay `ByteBuffer` đang cấp cho I/O đó?

**Đáp án:** Không mặc định. Timeout chỉ kết thúc việc chờ; I/O có thể còn chạy và đang sử dụng buffer.

**Câu 6.** Có thể gọi thêm `read(...)` trên một `AsynchronousSocketChannel` đang có một lần đọc chờ không?

**Đáp án:** Không; có thể gặp `ReadPendingException`. Cần đọc nối tiếp sau mỗi lần hoàn tất.

**Câu 7.** Vì sao handler có tham số `attachment`?

**Đáp án:** Để callback nhận ngữ cảnh gắn với thao tác, ví dụ offset, request id hoặc trạng thái, mà không phụ thuộc biến toàn cục dùng chung.

**Câu 8.** Nếu callback `failed(...)` chỉ ghi log mà không hoàn tất Promise/Future điều phối, điều gì xảy ra?

**Đáp án:** Thành phần đang chờ có thể treo vô hạn. Đường lỗi cũng phải công bố trạng thái kết thúc.

## 16. Ghi nhớ

- **`Future`:** nhận đối tượng đại diện kết quả; `get()` có thể chặn người đợi, lỗi thực thi nằm trong `ExecutionException`; timeout chờ không tự dừng I/O.
- **`CompletionHandler`:** đưa kết quả/lỗi qua `completed(...)` và `failed(...)`; attachment mang ngữ cảnh; callback phải ngắn, có kiểm soát trạng thái và báo lỗi.
- **Bất đồng bộ vẫn có partial I/O**: tiếp tục theo số byte trả về, không giả định một lần là đủ.
- **Buffer có ownership trong thời gian I/O đang chạy**; không tái sử dụng hoặc sửa buffer trước khi kết thúc.
- **Socket bất đồng bộ** cần điều phối số thao tác đang chờ, framing, backpressure và vòng đời kết nối.
- **Giải pháp đúng** là giải pháp có trạng thái kết thúc rõ ràng cho mọi thao tác: thành công, thất bại, timeout hoặc hủy có kiểm soát.
