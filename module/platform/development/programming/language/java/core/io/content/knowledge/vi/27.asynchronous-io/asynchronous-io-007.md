# Tiếp tục đọc ghi khi kết quả I/O bất đồng bộ chỉ hoàn tất một phần

## 1. Vấn đề cốt lõi: một operation hoàn thành không đồng nghĩa cả message hoàn tất

Trong Java NIO.2, **I/O bất đồng bộ** cho phép ứng dụng khởi động thao tác `read` hoặc `write` rồi nhận kết quả qua `Future` hoặc `CompletionHandler`. Một thao tác I/O đã **completed successfully** chỉ có nghĩa là *lượt thao tác đó* đã kết thúc theo hợp đồng của API. Nó **không hứa** đã chuyển hết những byte ứng dụng mong muốn.

Ví dụ bạn muốn gửi 100 byte:

~~~text
ByteBuffer cần ghi: 100 byte
     |
     +--> async write lần 1: completed(37)
     |         buffer còn 63 byte
     |
     +--> async write lần 2: completed(20)
     |         buffer còn 43 byte
     |
     +--> async write lần 3: completed(43)
               buffer hết byte --> message gửi hết từ phía local
~~~

Số byte `37, 20, 43` chỉ mang tính minh họa; kết quả thực tế phụ thuộc channel, OS, tải và thời điểm. Ngay cả khi mọi byte được **local write** chấp nhận, điều đó **không bảo đảm** peer đã nhận hay xử lý thành công.

Đối với đọc cũng tương tự: một yêu cầu nhận frame 100 byte có thể hoàn tất lần đầu với 12 byte. Muốn có đúng 100 byte, cần **tái gửi read** với buffer còn chỗ cho đến khi đủ hoặc gặp EOF/lỗi/deadline.

Quy tắc trung tâm:

> **Lấy số byte thực sự hoàn thành làm nguồn sự thật, giữ trạng thái của phần còn lại, chỉ khởi động operation kế tiếp khi operation trước đã kết thúc, và có điểm dừng rõ ràng.**

## 2. Phân biệt ba loại hoàn thành

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **I/O operation completed** | Một lời gọi `read`/`write` đã có result hoặc failure | `completed(12, attachment)` |
| **Buffer completed** | Buffer đích đã đầy để đọc, hoặc buffer nguồn đã hết để ghi | `!dst.hasRemaining()` hoặc `!src.hasRemaining()` |
| **Message/protocol completed** | Toàn bộ frame/request/response đúng giao thức đã được xử lý | Đã nhận đủ length-prefixed body và xác thực |

Trong TCP, ứng dụng tự xây **message framing**: length-prefix, delimiter hoặc fixed-length. Một lời gọi `AsynchronousSocketChannel.read(dst, handler)` không tương ứng một message. Trong file, việc đọc buffer chỉ xong một chunk; còn tệp lớn cần nhiều chunk và các file offset kế tiếp.

Đặc biệt: **async không có nghĩa `Future.get()` không block**. Lời gọi khởi động operation có thể trả sớm, nhưng `future.get()` đợi kết quả và chặn thread gọi. `CompletionHandler` phù hợp khi muốn tiếp tục hoàn toàn dựa trên callback; `Future` phù hợp với cách phối hợp việc đợi kết quả ở một thread cho phép chờ.

## 3. Kết quả read và write cần được hiểu thế nào?

### 3.1. Đọc vào ByteBuffer

Với các asynchronous read API trả `Integer`:

- **`n > 0`:** đã đọc đúng `n` byte. ByteBuffer đích được tăng `position` tương ứng; `limit` không tự thay đổi.
- **`n == 0`:** lượt đọc không chuyển byte nào (ví dụ khi buffer không có `remaining`; trường hợp khác tùy API). Không coi đây là EOF và không tạo vòng lặp retry nóng vô hạn.
- **`n == -1`:** end-of-stream khi không còn byte để đọc. Với socket TCP, đó là phía vào đã kết thúc; với file, đã đến EOF theo điều kiện đọc.
- **Failure:** nhận qua `CompletionHandler.failed(Throwable, A)` hoặc `Future.get()` ném `ExecutionException` (hoặc cancellation/interruption khác).

Ví dụ buffer 8 byte, `position=0`, `limit=8`; nếu `completed(3)`, giờ `position=3`, `remaining=5`. Gọi lại read trên **chính buffer** này (sau khi operation trước đã xong) có thể ghi thêm byte vào từ vị trí 3, không được `clear()` làm mất trạng thái đã nhận.

### 3.2. Ghi từ ByteBuffer

Với các asynchronous write API trả `Integer`:

- **`n > 0`:** `n` byte đã được lấy khỏi buffer nguồn cho lượt ghi; `position` tăng `n`.
- **`n == 0`:** chưa ghi được byte nào. Cần chính sách retry có kiểm soát/deadline, tránh callback tự lặp ngay liên tục.
- **`src.hasRemaining() == true` sau completion:** chưa ghi hết nội dung cần gửi; tiếp tục dùng buffer còn phần chưa ghi.
- **`src.hasRemaining() == false`:** tất cả byte thuộc buffer đã được chuyển qua các lời gọi write thành công. Với TCP, đây **không** phải xác nhận bên nhận đã đọc.
- **Failure:** dừng chuỗi thao tác, thông báo lỗi và xử lý trạng thái có thể đã ghi được một phần.

Trước khi gửi, buffer phải ở **read mode** (`flip()` nếu vừa `put(...)`). Nếu dùng `StandardCharsets.UTF_8.encode(text)`, buffer được trả sẵn để đọc. Không `clear()` hay `rewind()` giữa các lần partial write; làm vậy có thể gửi lại byte cũ.

### 3.3. Không dùng phép kiểm tra sai

~~~java
// Sai: completed() được gọi không chứng minh đã gửi hết.
channel.write(src, null, new CompletionHandler<Integer, Void>() {
    public void completed(Integer n, Void unused) {
        System.out.println("Đã xong toàn message"); // có thể sai
    }
    public void failed(Throwable ex, Void unused) {
        ex.printStackTrace();
    }
});
~~~

Đây là **đoạn phản ví dụ**, yêu cầu `channel` đã connected và các import thích hợp. Chính xác phải kiểm tra `n` và `src.hasRemaining()` rồi quyết định tiếp tục hay hoàn thành.

## 4. ByteBuffer: position, limit, flip, compact là phần của thuật toán

ByteBuffer là nơi giữ **trạng thái đang đọc/ghi dở**. Một số chuyển trạng thái cần nắm:

| Thao tác | Tác dụng | Khi nào nên dùng |
|---|---|---|
| `clear()` | `position=0`, `limit=capacity`; **không xóa dữ liệu vật lý** | Bắt đầu fill một chunk mới khi dữ liệu cũ đã xử lý xong |
| `flip()` | `limit=position`, `position=0` | Chuyển buffer đã nhận/đã ghi bằng `put` sang chế độ đọc |
| `compact()` | Đưa byte còn lại từ `position..limit` về đầu rồi chuyển sang chế độ ghi | Parser đọc được một phần frame, còn dư byte chưa xử lý |
| `hasRemaining()` | `position < limit` | Kiểm tra còn byte cần ghi hoặc còn khoảng trống nhận |
| `remaining()` | `limit - position` | Tính byte còn lại, kiểm tra độ dài |
| `get()`/`put()` | Đọc/ghi tương đối và tăng position | Parser/serializer |

Với **socket read**, nếu application đang lắp frame 12 byte trong một buffer capacity 12:

~~~java
ByteBuffer dst = ByteBuffer.allocate(12);
// read lần 1 nhận 5 byte -> position = 5
// read lần 2 nhận 4 byte -> position = 9
// read lần 3 nhận 3 byte -> position = 12
dst.flip(); // bây giờ parse đúng 12 byte
~~~

Đây là **mã giải thích trạng thái**, không phải chương trình I/O chạy độc lập. Các read giả định hoàn tất tuần tự và buffer chưa bị thao tác trong lúc I/O pending.

**Không gọi `flip()` sau mỗi partial read khi đang cố fill một buffer cố định.** Chỉ flip khi đã nhận đủ vùng cần đọc hoặc khi chủ đích chuyển sang pha xử lý dữ liệu hiện có. Nếu parser tiêu thụ một số byte nhưng còn fragment của frame, dùng `compact()` để giữ fragment.

## 5. Future và CompletionHandler: hai cách tiếp tục

### 5.1. Future<Integer>

`AsynchronousFileChannel.read(dst, filePosition)`, `write(src, filePosition)` và `AsynchronousSocketChannel.read(dst)`/`write(src)` có overload trả `Future<Integer>`.

Một quy trình đơn giản:

~~~java
Future<Integer> pending = asyncFile.read(dst, fileOffset);
int n = pending.get(); // chờ completion; thread gọi bị block
// Sau khi get thành công, dst.position() đã phản ánh byte nhận được.
// Nếu vẫn chưa đủ dữ liệu, khởi tạo một read mới ở fileOffset + n.
~~~

Đây là mã minh họa với `AsynchronousFileChannel asyncFile`, `ByteBuffer dst`, `long fileOffset` có sẵn. `Future.get()` có thể ném `InterruptedException` hoặc `ExecutionException`; code cần chính sách xử lý/cancellation.

Điểm lợi là dễ viết vòng lặp tuần tự, dễ giải thích tính đúng đắn. Điểm hạn chế là thread `get()` phải chờ; nó không biến chương trình thành callback-driven nonblocking processing.

### 5.2. CompletionHandler<V,A>

Callback style trả kết quả qua:

~~~java
void completed(V result, A attachment);
void failed(Throwable exc, A attachment);
~~~

`V` thường là `Integer` cho một buffer, `Long` cho scattering/gathering nhiều buffer, hoặc `Void` cho connect. `A` là **attachment** do ứng dụng chọn để giữ trạng thái của operation, chẳng hạn file offset, ByteBuffer, request ID hoặc đối tượng phiên.

Trong `completed`:

1. Nếu `n > 0`, cập nhật offset theo **số byte thực tế** (khi API có offset).
2. Kiểm tra `ByteBuffer.hasRemaining()`.
3. Nếu còn dữ liệu, gọi tiếp asynchronous read/write với buffer và offset đúng.
4. Nếu đã đủ, hoàn thành operation ở cấp **message**, báo cho phần tiếp theo và giải phóng ownership.
5. Nếu gặp `n == 0` hoặc failure, dùng retry policy/deadline thích hợp; không tự tạo vòng lặp bất tận hoặc nuốt exception.

Trong `failed`, phải kết thúc/chuyển trạng thái request, không để `CompletableFuture`/latch chờ vô thời hạn. Completion handler nên ngắn; xử lý CPU nặng nên chuyển sang executor ứng dụng nếu cần.

## 6. AsynchronousFileChannel: offset là bắt buộc và độc lập

Khác với `FileChannel` có **current file position**, `AsynchronousFileChannel` **không có một current position chung**. Mỗi lời gọi `read`/`write` truyền **file position** dạng `long`. Ví dụ:

~~~java
Future<Integer> readFuture = input.read(dst, 100L);
int bytesRead = readFuture.get();
// Nếu cần đọc tiếp liên tiếp trong file: vị trí kế tiếp là 100L + bytesRead.
~~~

Mã minh họa: đây là offset **trong file**, không phải `ByteBuffer.position()`. Phải quản lý hai con số:

- `fileOffset`: byte index trong file.
- `buffer.position()`: vị trí trong vùng buffer cho lần I/O kế tiếp.

Hai chỉ số này không tự đồng bộ với nhau. Sau một write chỉ hoàn thành `n` byte, **write lại tại `fileOffset + n`** với buffer đã có position tăng n. Nếu giữ offset cũ cho partial write kế tiếp, dữ liệu mới có thể đè lên vùng vừa ghi. Nếu tự cộng thêm cả `buffer.position()` một lần nữa, có thể tạo khoảng trống hoặc bỏ byte.

`AsynchronousFileChannel` cho phép **nhiều I/O cùng outstanding**, nhưng thứ tự hoàn thành và thứ tự callback không được bảo đảm. Không khởi chạy hàng loạt write có vùng file chồng lấn rồi giả định chúng sẽ tuần tự đúng thứ tự được submit. Một `ByteBuffer` cũng không an toàn khi đồng thời dùng cho nhiều I/O đang pending.

### Ví dụ minh họa diễn tiến

~~~text
File nguồn:      A B C D E F G H I J
Buffer capacity: 6

read(dst, offset=0)  -> n=4, dst.position=4
read(dst, offset=4)  -> n=2, dst.position=6
flip()              -> chuẩn bị ghi 6 byte A..F

write(src, offset=0) -> n=3, src.position=3
write(src, offset=3) -> n=3, src.position=6 (hết chunk)

Đọc chunk tiếp:
read(dst, offset=6) -> ... cho đến EOF
~~~

Các số `4,2,3,3` là ví dụ, không có cam kết đó là số byte kết quả trên máy cụ thể.

## 7. Chương trình Java 17+ chạy được: copy bằng asynchronous file channels

Chương trình thực sự copy nội dung tệp bằng `AsynchronousFileChannel`, không giả định mỗi read/write trả đủ toàn buffer.

- **Cố ý dùng buffer capacity 4 byte** cho file 21 byte, nên chắc chắn cần nhiều lượt đọc/ghi theo từng chunk.
- Vòng ngoài đọc từ file nguồn với offset tăng theo `read` thực tế.
- Vòng trong ghi hết byte của chunk từ buffer với offset tăng theo `written` thực tế.
- `Future.get()` khiến ví dụ dễ quan sát và **đồng bộ tại điểm đợi**. Các I/O vẫn được khởi tạo qua asynchronous channel.
- Vì ví dụ không cần mô phỏng backpressure, nếu một I/O trả 0 bất ngờ trên buffer còn dữ liệu, chương trình **dừng có báo lỗi** thay vì vòng lặp nóng vô hạn; sản phẩm thật có thể triển khai retry có deadline và scheduling.

**Tệp `AsyncPartialDemo.java`:**

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;

public class AsyncPartialDemo {
    public static void main(String[] args) throws Exception {
        Path source = Files.createTempFile("async-source-", ".txt");
        Path target = Files.createTempFile("async-target-", ".txt");
        byte[] expected =
                "async-data-0123456789".getBytes(StandardCharsets.UTF_8);

        try {
            Files.write(source, expected);
            long copied = 0L;

            try (AsynchronousFileChannel input =
                         AsynchronousFileChannel.open(
                                 source, StandardOpenOption.READ);
                 AsynchronousFileChannel output =
                         AsynchronousFileChannel.open(
                                 target, StandardOpenOption.WRITE,
                                 StandardOpenOption.TRUNCATE_EXISTING)) {

                ByteBuffer buffer = ByteBuffer.allocate(4);
                long readOffset = 0L;
                long writeOffset = 0L;

                for (;;) {
                    buffer.clear();
                    int read = input.read(buffer, readOffset).get();

                    if (read == -1) {
                        break; // Hết file nguồn.
                    }
                    if (read == 0) {
                        throw new IOException("No read progress");
                    }

                    readOffset += read;
                    buffer.flip();

                    while (buffer.hasRemaining()) {
                        int written =
                                output.write(buffer, writeOffset).get();

                        if (written <= 0) {
                            throw new IOException("No write progress");
                        }
                        writeOffset += written;
                    }
                }
                copied = writeOffset;
            }

            System.out.println("bytes=" + copied);
            System.out.println("equal=" +
                    Arrays.equals(expected, Files.readAllBytes(target)));
            System.out.println("text=" + Files.readString(target));
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AsyncPartialDemo.java
java AsyncPartialDemo
~~~

**Stdout đã kiểm chứng trên JDK:**

~~~text
bytes=21
equal=true
text=async-data-0123456789
~~~

Ý nghĩa:

1. 21 byte không thể nằm hết trong buffer 4 byte; chương trình phải xử lý nhiều chunk.
2. `input.read(buffer, readOffset).get()` chỉ chờ **một read operation**. Số byte thành công `read` được cộng vào offset nguồn.
3. `buffer.flip()` chuẩn bị đúng các byte đã đọc để ghi, không bao gồm byte cũ của buffer.
4. `while(buffer.hasRemaining())` là nơi xử lý **partial write** nếu channel ghi ít byte hơn mong muốn; `writeOffset` tăng bằng `written` thực tế.
5. Khi `read == -1`, vòng lặp dừng vì EOF. Sau khi đóng channel, chương trình xác nhận file đích có đúng nội dung.

Do chương trình dùng `Future.get()`, mỗi iteration chờ completion trước khi dùng lại buffer. Trong pipeline callback thật, phải giữ **ownership** của buffer cho tới callback mới xử lý/tái sử dụng nó.

## 8. Resubmit bằng CompletionHandler: mẫu partial write

Muốn tránh chặn thread bằng `get()`, handler có thể tự khởi động một write tiếp theo sau khi callback trước hoàn thành. Trong ví dụ sau, `AsynchronousFileChannel` cho phép truyền file offset một cách tường minh.

**Đoạn mã minh họa đặt trong một lớp đã có các import liên quan:**

~~~java
static CompletableFuture<Void> writeAll(
        AsynchronousFileChannel channel,
        ByteBuffer src,
        long startOffset) {

    CompletableFuture<Void> done = new CompletableFuture<>();

    if (!src.hasRemaining()) {
        done.complete(null);
        return done;
    }

    CompletionHandler<Integer, Long> handler =
            new CompletionHandler<>() {
        @Override
        public void completed(Integer n, Long offset) {
            if (n <= 0) {
                done.completeExceptionally(
                        new IOException("Write did not progress"));
                return;
            }

            long nextOffset = offset + n;
            if (!src.hasRemaining()) {
                done.complete(null);
                return;
            }

            try {
                channel.write(src, nextOffset, nextOffset, this);
            } catch (RuntimeException ex) {
                done.completeExceptionally(ex);
            }
        }

        @Override
        public void failed(Throwable exc, Long offset) {
            done.completeExceptionally(exc);
        }
    };

    channel.write(src, startOffset, startOffset, handler);
    return done;
}
~~~

Đây là **phương thức minh họa, không phải chương trình Java độc lập**; lớp chứa nó cần import `java.nio.ByteBuffer`, `java.nio.channels.AsynchronousFileChannel`, `java.nio.channels.CompletionHandler`, `java.io.IOException` và `java.util.concurrent.CompletableFuture`. Đầu vào `channel` đang open để ghi, `startOffset >= 0` và `src` phải ở read mode.

Cách nó tiếp tục partial write:

- Lượt đầu `channel.write(src, startOffset, startOffset, handler)` gắn attachment `Long` chính là file offset của lượt vừa khởi tạo.
- Callback `completed(n, offset)` chạy khi operation đó kết thúc. `src.position()` đã được cập nhật theo n byte đã viết.
- Nếu còn dữ liệu, handler gửi tiếp `write(src, offset+n, offset+n, this)`.
- Nếu không còn dữ liệu, `done.complete(null)` đánh dấu **toàn buffer** đã được chuyển hết, không chỉ một lượt.
- Nếu failure hoặc không tiến triển trong ví dụ, `done.completeExceptionally(...)` khiến caller có thể quan sát lỗi.

**Về `n == 0`:** đoạn minh họa cố ý kết thúc với lỗi nếu không tiến triển thay vì tạo vòng callback bận. Trong ứng dụng production, có thể **lập lịch retry sau**, dùng retry budget/deadline/backoff hoặc xác định provider/backend không tiến triển. Không coi việc resubmit lập tức vô hạn khi `n==0` là giải pháp tổng quát.

**Về recursion/ordering:** callback có thể được dispatch rất nhanh và ở một số implementation có thể chạy trực tiếp trên thread khởi tạo theo hợp đồng. Nếu chuỗi callback rất dài, cần cân nhắc chuyển bước tiếp sang executor/trampoline để tránh recursion sâu hoặc chiếm thread completion. Cũng không được sửa hoặc dùng lại `src` ở thread khác trong lúc mỗi operation còn pending.

## 9. Tiếp tục partial read trong CompletionHandler

Muốn đọc **đúng N byte** cho một TCP frame fixed-length, buffer cần đặt `limit` để `remaining() == N` lúc khởi động. Sau mỗi completion:

- `n > 0` và buffer còn chỗ: gửi tiếp một `read` mới trên cùng buffer.
- `n > 0`, buffer hết chỗ: frame đủ N byte; `flip()` rồi xử lý.
- `n == -1` trước khi nhận đủ: remote đóng output sớm; frame bị truncate. Đây là **lỗi framing** dù EOF là kết quả I/O hợp lệ.
- `n == 0` khi vẫn còn chỗ: không tuyên bố EOF và tránh retry nóng; áp dụng chính sách chờ/retry với deadline.
- `failed(exc)`: kết thúc frame có lỗi và dọn tài nguyên theo ownership.

Pseudocode Java theo mô hình callback (không phải chương trình độc lập):

~~~java
channel.read(dst, state, new CompletionHandler<Integer, State>() {
    @Override
    public void completed(Integer n, State s) {
        if (n == -1) {
            s.fail(new EOFException("Incomplete frame"));
            return;
        }

        if (!dst.hasRemaining()) {
            dst.flip();
            s.completeFrame(dst);
            return;
        }

        if (n == 0) {
            s.scheduleRetry(); // deadline/retry policy của ứng dụng
            return;
        }

        channel.read(dst, s, this); // chỉ sau completion trước
    }

    @Override
    public void failed(Throwable exc, State s) {
        s.fail(exc);
    }
});
~~~

Trong pseudocode này, `State` và `scheduleRetry()` là abstraction ứng dụng **chưa được định nghĩa**, nên **không thể compile độc lập**. `scheduleRetry()` phải biết cách tái gửi một read duy nhất vào đúng channel/buffer khi phù hợp, tránh nhiều operation outstanding; không phải phương thức tích hợp của Java. `s.completeFrame(dst)` phải chuyển ownership buffer an toàn.

Một lựa chọn khác với protocol **length-prefixed** là trước tiên đọc đủ header (ví dụ 4 byte), giải mã độ dài theo endian quy định, validate size, sau đó cấp buffer body hoặc duy trì state machine để đọc đủ body. Không được tin length từ peer khi chưa giới hạn kích thước tối đa.

## 10. Khác nhau giữa AsynchronousSocketChannel và AsynchronousFileChannel

| Đặc điểm | AsynchronousSocketChannel | AsynchronousFileChannel |
|---|---|---|
| Mô hình dữ liệu | TCP stream không có message boundary | Tệp byte có file offset |
| Offset trong lời gọi | `read(dst)`/`write(src)` không nhận explicit file offset | `read(dst, position)`/`write(src, position)` |
| Số I/O đồng thời | Tối đa một read pending và một write pending trên socket channel | Nhiều read/write có thể pending; thứ tự không bảo đảm |
| Overlap | Read mới trước khi read cũ xong: `ReadPendingException`; write tương tự `WritePendingException` | Không dùng chung một ByteBuffer cho I/O đồng thời; tránh ghi vùng file chồng lấn không có thứ tự |
| EOF | `read == -1` khi stream đầu vào kết thúc | `read == -1` khi đã tới EOF file |
| Deadline | Overload read/write có timeout (CompletionHandler) | Thường quản lý deadline/cancellation ở tầng ứng dụng |
| Failure đặc biệt | `InterruptedByTimeoutException`; trạng thái channel/buffer có thể không xác định sau timeout | `ExecutionException` bao bọc lỗi Future; close với pending I/O có thể kết thúc `AsynchronousCloseException` |

Với socket, tại một thời điểm có thể có **một read và một write outstanding đồng thời**, nhưng không được khởi tạo read thứ hai khi read đầu còn pending. Nếu dùng callback để re-read, chính callback completion là vị trí tự nhiên khởi tạo read tiếp; tương tự cho write. Nếu luồng khác cũng đọc/ghi cùng socket, cần một bộ điều phối đảm bảo không gửi trùng operation.

**Đặc biệt với timeout:** Java 17 cảnh báo nếu timeout xảy ra khi không thể xác định chính xác bao nhiêu byte đã được đọc/ghi, buffer và trạng thái một chiều I/O của socket có thể ở trạng thái implementation-specific, các operation tiếp có thể ném runtime exception không xác định. Không tự động retry trên chính buffer/channel như thể không byte nào đã truyền; thường cần đóng kết nối hoặc tái đồng bộ giao thức có chủ đích. 

## 11. Buffer ownership và an toàn đồng thời

Một `ByteBuffer` đang được dùng cho asynchronous read/write **không an toàn nếu ứng dụng đồng thời thay đổi** `position`, `limit` hoặc nội dung trước khi operation hoàn tất. Đây là nguồn lỗi rất khó tái hiện.

Các quy tắc quan trọng:

1. **Một owner tại một thời điểm.** Khi submit I/O, trao ownership buffer cho operation/handler tới khi completion hoặc failure được xử lý.
2. **Không `clear`/`flip`/`put` vào buffer đang pending** từ thread khác. Buffer position có thể đang bị thay đổi bởi operation.
3. **Không dựa vào thứ tự callback của các AsynchronousFileChannel operation khác nhau**. Ghi không chồng lấn và quản lý offset rõ ràng.
4. **AsynchronousSocketChannel chỉ cho một read và một write pending**. Điều này không đồng nghĩa thread-safe cho business state hay ByteBuffer chung.
5. **Truyền buffer và offset trong một state/attachment** để tránh đụng biến dùng chung giữa các kết nối.
6. **Khi yêu cầu bị hủy**, xác định operation còn có thể hoàn thành/tác động buffer hay không theo hợp đồng API; tránh tái dùng buffer quá sớm. Với `Future.cancel`, hậu quả có thể phụ thuộc việc I/O đã hoàn thành hoặc cancellation có đóng channel.

Mô hình state machine cho một buffer ghi:

~~~text
NEW
 |
 +-- submit write ---> PENDING
                          |
                  completed(n > 0)
                          |
                 +--------+---------+
                 |                  |
           hasRemaining         no remaining
                 |                  |
              PENDING            COMPLETE
                 |
         failed / timeout
                 |
               FAILED
~~~

Khi nhiều request chia sẻ một TCP connection, cần queue các thông điệp đầu ra để một writer điều phối duy nhất giữ **thứ tự byte giao thức**. Không nên mở hai asynchronous writes trên cùng socket rồi mặc định chúng tự được nối theo thứ tự mong muốn.

## 12. Xử lý lỗi, zero progress, EOF và cancellation

### EOF không phải zero

- **`-1`:** luồng/tệp đã kết thúc theo hợp đồng read; nếu đang nhận frame cố định mà chưa đủ byte, báo frame bị thiếu.
- **`0`:** lượt này không chuyển byte. Không kết luận remote đã đóng; chọn retry policy hợp lý. Với buffer hết remaining, việc trả 0 là hiển nhiên.
- **`n > 0`:** có tiến triển; tiếp tục tới khi đạt điều kiện đủ dữ liệu.

### Tránh retry vô hạn khi trả 0

Trong thực tế, nếu hệ thống/backend có thể trả 0 nhiều lần, cần một trong các chiến lược: lịch retry bất đồng bộ theo thời điểm; deadline timeout của operation/request; giới hạn số lần không tiến triển; hoặc chờ readiness theo API phù hợp. **Không `while(true)` bận** gọi lập tức cùng operation từ completion handler mỗi khi `n==0`.

### Tách lỗi I/O với lỗi logic giao thức

Ví dụ `read == -1` là EOF hợp lệ ở cấp stream nhưng là **lỗi application** nếu body mới nhận 10/100 byte. `write` hoàn thành không đồng nghĩa peer đã phản hồi. `ExecutionException` từ `Future.get` chứa root cause I/O; nên kiểm tra `getCause()`. Với `InterruptedException`, cân nhắc phục hồi interrupt flag và dừng tác vụ theo chính sách. Với timeout/cancellation, không được kết luận buffer chắc chắn chưa bị thay đổi nếu Javadoc không hứa.

### Close và tài nguyên

`AsynchronousFileChannel`/`AsynchronousSocketChannel` triển khai `AutoCloseable`. Dùng `try-with-resources` cho phạm vi sở hữu. Không đóng channel trong lúc callback còn cần nó hoặc khi operation đang pending, trừ khi đó chính là chính sách hủy: close có thể khiến outstanding operations kết thúc bằng `AsynchronousCloseException`. Đối với hệ thống server, quản lý vòng đời channel group, worker executor và queue độc lập với buffer/channels.

## 13. Cách áp dụng vào giao thức thực tế

**TCP length-prefixed message:**

1. Đọc đủ 4 byte header bằng vòng read/callback có trạng thái.
2. `flip` header, đọc độ dài theo `ByteOrder` đã thống nhất và validate tối đa.
3. Cấp buffer body đúng dung lượng (hoặc stream theo chunk nếu body lớn).
4. Tiếp tục đọc body tới khi buffer đầy; EOF trước khi đủ là frame lỗi.
5. Xử lý body sau khi I/O completed và chuyển ownership; nếu có nhiều message trong stream, giữ buffer dư và state parser.

**Gửi response:**

1. Serialize header + body ra các ByteBuffer sẵn để đọc.
2. Submit write đầu tiên.
3. Sau completion, kiểm tra số byte và `hasRemaining`; tiếp tục phần chưa ghi.
4. Chỉ chuyển sang message tiếp theo khi các buffer hiện tại hết byte hoặc quy tắc framing cho phép.
5. Nếu write bị fail hoặc timeout, cập nhật trạng thái request; đừng âm thầm loại các byte chưa gửi.

**Copy file bằng async file channels:**

1. Đặt file offset nguồn/đích riêng.
2. Đọc một chunk; cộng source offset theo bytesRead.
3. `flip` buffer; ghi tới hết chunk; cộng target offset theo bytesWritten.
4. `clear` buffer sau khi cả chunk đã ghi xong; đọc chunk tiếp.
5. Khi EOF, chỉ báo hoàn thành sau khi mọi write đã được xác nhận.

## 14. Các lỗi phổ biến

1. **“CompletionHandler.completed nghĩa là message hoàn tất.”** Sai: result có thể nhỏ hơn expected.
2. **“`Future.get()` trả xong là đã đọc hết buffer.”** Sai: mới hoàn thành một operation.
3. **“Một TCP read là một message.”** Sai: TCP stream cần framing.
4. **“`read()==0` tức EOF.”** Sai: EOF có mã `-1`.
5. **“`write()` luôn chuyển hết `remaining`.”** Sai: kiểm tra số byte và gửi tiếp.
6. **“Partial write xong cứ `rewind()` rồi ghi lại.”** Sai: gửi lặp byte cũ.
7. **“Sau mỗi partial read, gọi `clear()` cho lần kế tiếp.”** Sai: có thể mất fragment mới nhận.
8. **“AsynchronousFileChannel tự tăng current file position.”** Sai: không có current position chung; offset do caller quản lý.
9. **“Sau write n byte, chỉ cần tăng file offset theo capacity buffer.”** Sai: cộng đúng `n`.
10. **“Có thể bắt đầu hai async read trên một AsynchronousSocketChannel.”** Sai: `ReadPendingException`; tương tự write pending.
11. **“AsynchronousFileChannel callback luôn gọi theo thứ tự submit.”** Sai: thứ tự không được bảo đảm.
12. **“ByteBuffer đang pending dùng lại ở thread khác vẫn an toàn.”** Sai: phải bảo vệ ownership tới khi operation hoàn thành.
13. **“Callback `n == 0` thì retry liên tục càng nhanh.”** Sai: dễ busy-spin; cần chính sách chờ.
14. **“Timeout nghĩa là không byte nào đã được chuyển.”** Sai: một số asynchronous socket timeout có trạng thái buffer/I/O không xác định.
15. **“Local write hết byte chứng minh peer đã xử lý.”** Sai: cần response/ACK theo giao thức ứng dụng.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Một `ByteBuffer` có `remaining=40`; callback write trả `12`. Bước tiếp theo?

**Đáp án:** Buffer tự có position tăng 12; còn 28 byte. Chờ completion trước đó đã xong, khởi tạo write tiếp theo cho phần còn lại, không `rewind` buffer.

**Câu 2.** Một TCP frame cần 100 byte; read callback trả `30` rồi `-1`. Có được coi đã nhận thành công?

**Đáp án:** Không. Stream đã EOF trước khi frame đủ 100 byte; đó là truncated frame ở cấp giao thức.

**Câu 3.** `AsynchronousFileChannel.write(src, 50)` hoàn thành `n=7` nhưng buffer vẫn còn byte. File position lần tiếp theo là bao nhiêu?

**Đáp án:** `57`; buffer position đã tăng 7 để bắt đầu từ phần chưa ghi.

**Câu 4.** Với `AsynchronousSocketChannel`, có thể submit read thứ hai ngay khi read trước còn pending?

**Đáp án:** Không; `ReadPendingException`. Phải nối tiếp sau completion hoặc điều phối state để chỉ có một read pending.

**Câu 5.** Vì sao ví dụ `Future.get()` vẫn là I/O bất đồng bộ ở cấp channel nhưng code nhìn giống blocking?

**Đáp án:** Operation khởi tạo trên asynchronous channel và trả Future. Tuy vậy caller gọi `get()` đã chủ động block để chờ completion; callback có thể giúp tránh việc chờ theo kiểu này.

### Tài liệu chính thức

- [Java 17 — AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html)
- [Java 17 — AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html)
- [Java 17 — AsynchronousByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousByteChannel.html)
- [Java 17 — CompletionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html)
- [Java 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
