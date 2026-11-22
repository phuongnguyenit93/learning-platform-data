# Đọc ghi theo vị trí thay vì con trỏ dùng chung — AsynchronousFileChannel trong Java

## 1. Vấn đề cần giải quyết

Một file có thể chứa các khối dữ liệu độc lập:

~~~text
Offset tính theo byte:
0       4       8      12
|-------|-------|-------|
ABCD    EFGH    IJKL
~~~

Nếu nhiều tác vụ liên tục đổi **vị trí đọc/ghi hiện tại** của cùng một channel, việc phối hợp để không đọc nhầm vùng có thể phức tạp. Java cung cấp `java.nio.channels.AsynchronousFileChannel` với đặc điểm quan trọng:

**AsynchronousFileChannel không có con trỏ current file position dùng chung.** Mỗi thao tác read/write phải chỉ rõ **vị trí byte trong file**.

~~~java
Future<Integer> a = channel.read(bufferA, 0L);
Future<Integer> b = channel.read(bufferB, 8L);
Future<Integer> c = channel.write(bufferC, 4L);
~~~

Đây là đoạn minh họa trong một phương thức: `channel` đã được mở đúng quyền, mỗi buffer thuộc riêng một thao tác. Ba số `0L`, `8L` và `4L` là **offset byte từ đầu file**, không phải vị trí của bộ đệm và không phụ thuộc số lần đọc/ghi trước đó.

Mỗi lời gọi trả `Future<Integer>`; I/O có thể **chưa hoàn tất** tại thời điểm lời gọi trả về. Lựa chọn `get()` để chờ hay sử dụng `CompletionHandler` là một phần thiết kế riêng.

### Những kiến thức cần nắm

1. Hiểu rõ file offset, shared cursor, ByteBuffer position và kích thước file.
2. Phân biệt cách đọc tuần tự của `FileChannel` và cách đọc **theo vị trí** của `AsynchronousFileChannel`.
3. Đọc/ghi qua `read(ByteBuffer,long)` và `write(ByteBuffer,long)` với `Future<Integer>`.
4. Nhận completion qua `CompletionHandler<Integer,A>` và attachment.
5. Xử lý partial reads/writes, EOF, kết quả 0, exception và timeout.
6. Không dùng chung một ByteBuffer cho nhiều I/O đang chờ.
7. Hiểu phép đọc/ghi theo **byte**, đặc biệt khi dữ liệu là UTF-8.
8. Khởi phát nhiều operations với **offset không chồng lấn**, không dựa vào thứ tự hoàn tất.
9. Phân biệt `size`, `truncate`, `force`, ghi ngoài EOF, executor và vòng đời channel.
10. Thiết kế offset allocator, ghi record, xử lý lỗi/synchronization và bảo mật.

**Bối cảnh phiên bản:** `AsynchronousFileChannel` có từ **Java 7** và vẫn là API hiện hành. Các chương trình hoàn chỉnh trong bài sử dụng **Java 17+**, thêm `Files.writeString/readString` (Java 11+) cho fixture. Các kiến thức API được đối chiếu với Javadoc Java SE 26; không dựa vào kỹ thuật legacy.

**Kiểm chứng:** 11 chương trình dưới đây đã được biên dịch bằng `javac -encoding UTF-8 --release 17` và chạy thành công trên JDK 17. Output in **sau khi chờ thao tác hoàn tất** để không phụ thuộc lịch thread; thời gian/hiệu năng vẫn phụ thuộc filesystem/provider.

## 2. Vị trí byte trong file không phải vị trí trong ByteBuffer

Với file `ABCDEFGHIJ`:

~~~text
File offset    0 1 2 3 4 5 6 7 8 9
File contents  A B C D E F G H I J
                         ^
                    offset = 4
~~~

`channel.read(dst,4L)` yêu cầu đọc từ byte `E`. Số byte tối đa phụ thuộc `dst.remaining()` tại thời điểm khởi phát.

Trong khi đó, `ByteBuffer` có ba thuộc tính riêng:

- `capacity`: sức chứa của buffer.
- `position`: vị trí hiện tại **trong buffer**.
- `limit`: giới hạn phần có thể truy cập; `remaining = limit - position`.

Ví dụ:

~~~text
Buffer capacity=5, position=0, limit=5
read từ file -> nhận 3 byte "ABC"
Buffer position=3, limit=5
flip() -> position=0, limit=3
Đọc "ABC" từ buffer; clear() chuẩn bị buffer cho lượt I/O tiếp
~~~

**`flip()` và `clear()` chỉ thay đổi trạng thái của ByteBuffer**, không đặt vị trí file. `clear()` cũng không xóa vật lý dữ liệu cũ trong bộ nhớ.

### 2.1. Offset tính theo byte, không theo ký tự

UTF-8 dùng số byte biến thiên cho mỗi ký tự. `"Café"` có **4 ký tự** nhưng mã hóa thành **5 byte**. Nếu cần ghi đúng khối trong file binary, phải lấy độ dài từ `"Café".getBytes(StandardCharsets.UTF_8).length`, không dùng `String.length()` để tính số byte.

Một file text có nhiều ký tự Unicode không cho phép suy ra byte offset chỉ bằng character index. Muốn đọc một đoạn text giữa file, cần quy tắc encoding/layout, không tự cắt giữa các byte tạo nên một ký tự.

## 3. API và những hợp đồng quan trọng

| API | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `read(ByteBuffer dst,long position)` | `Future<Integer>` | Đọc tối đa `dst.remaining()` byte từ offset được chỉ định |
| `write(ByteBuffer src,long position)` | `Future<Integer>` | Ghi các byte còn lại của src vào offset |
| `read(dst,pos,attachment,handler)` | `void` | Gọi `completed/failed` khi xong |
| `write(src,pos,attachment,handler)` | `void` | Gọi `completed/failed` khi xong |
| `size()` | `long` | Lấy kích thước file hiện hành |
| `truncate(long)` | channel | Thu nhỏ file nếu kích thước chỉ định nhỏ hơn size hiện hành |
| `force(boolean)` | `void` | Đẩy thay đổi đã hoàn tất tới storage theo semantics |
| `lock(...)` / `tryLock(...)` | `FileLock` hoặc Future/handler | Khóa file/vùng file theo provider |

**Lưu ý:** `size()`, `truncate()` và `force()` là những method đồng bộ, dù thuộc một class có tên Asynchronous.

### 3.1. Mở channel đúng quyền

~~~java
try (AsynchronousFileChannel channel =
         AsynchronousFileChannel.open(
             path,
             StandardOpenOption.READ,
             StandardOpenOption.WRITE)) {
    // I/O theo offset.
}
~~~

Đây là đoạn trong một phương thức có `path` kiểu `Path`, xử lý/khai báo ngoại lệ.

Các lựa chọn hiện hành thường gặp:

- `READ`: cho phép đọc.
- `WRITE`: cho phép ghi.
- `CREATE`: tạo file nếu chưa có khi mở để ghi.
- `CREATE_NEW`: tạo mới và từ chối nếu tên file đã tồn tại.
- `TRUNCATE_EXISTING`: rút file cũ về 0 byte khi mở để ghi — dễ mất dữ liệu nếu dùng nhầm.
- `SYNC` và `DSYNC`: chính sách đồng bộ dữ liệu/metadata.
- `SPARSE`: gợi ý khi tạo file sparse.
- `DELETE_ON_CLOSE`: yêu cầu nỗ lực xóa file khi đóng theo provider.

Nếu mở channel chỉ `READ` rồi gọi write, bạn có thể nhận `NonWritableChannelException`. Offset âm gây `IllegalArgumentException`.

**Không suy diễn chế độ `APPEND` có shared cursor cho AsynchronousFileChannel.** Các lựa chọn chuẩn liệt kê trong Javadoc `open` không mô tả APPEND như một chế độ nối tự động. Lấy `size()` rồi ghi tại cuối file từ nhiều threads **không tự an toàn**, vì nhiều writers có thể đọc cùng size.

### 3.2. So sánh với FileChannel

`FileChannel.read(ByteBuffer)` dùng **current channel position** rồi cập nhật nó. Nhưng `FileChannel.read(ByteBuffer,long)` cũng hỗ trợ **positional I/O** và không thay current position.

`AsynchronousFileChannel` khác ở chỗ **không hề có current channel position**: mọi read/write có offset, và completion qua Future hoặc CompletionHandler. Đừng nói sai rằng chỉ asynchronous channel mới có thao tác đọc theo vị trí.

Nguồn: [AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html), [FileChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/FileChannel.html).

## 4. Ví dụ 1 — Đọc hai vùng file theo hai offset

Tạo `OffsetReadDemo.java`:

~~~java
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.concurrent.*;
import static java.nio.file.StandardOpenOption.*;

public class OffsetReadDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("offset-read-", ".txt");
        try {
            Files.writeString(
                    file, "ABCDEFGHIJKL", StandardCharsets.US_ASCII);

            try (AsynchronousFileChannel ch =
                    AsynchronousFileChannel.open(file, READ)) {
                ByteBuffer buf = ByteBuffer.allocate(4);

                int first = ch.read(buf, 8L)
                        .get(5, TimeUnit.SECONDS);
                buf.flip();
                String at8 =
                        StandardCharsets.US_ASCII.decode(buf).toString();

                buf.clear();
                int second = ch.read(buf, 2L)
                        .get(5, TimeUnit.SECONDS);
                buf.flip();
                String at2 =
                        StandardCharsets.US_ASCII.decode(buf).toString();

                System.out.println("bytesAt8=" + first);
                System.out.println("textAt8=" + at8);
                System.out.println("bytesAt2=" + second);
                System.out.println("textAt2=" + at2);
                System.out.println("size=" + ch.size());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 --release 17 OffsetReadDemo.java
java OffsetReadDemo
~~~

Stdout:

~~~text
bytesAt8=4
textAt8=IJKL
bytesAt2=4
textAt2=CDEF
size=12
~~~

**Phân tích:**

1. File có 12 byte ASCII.
2. `read(buf,8L)` đọc bốn byte `IJKL`; `Future.get(5,SECONDS)` chờ kết quả.
3. `flip()` chuyển buffer sang trạng thái đọc các bytes vừa nhận.
4. `clear()` chuẩn bị buffer cho lần I/O thứ hai **sau khi Future trước đã hoàn tất**.
5. `read(buf,2L)` đọc `CDEF` mà không cần “seek channel”.
6. `size()` trả 12 vì không có thao tác sửa file.

**Không nhầm:** I/O được khởi phát bất đồng bộ, nhưng thread gọi `get()` vẫn có thể phải **chờ**. Muốn thực hiện công việc khác trong khi I/O diễn ra, đừng gọi get ngay hoặc sử dụng completion handler/điều phối phù hợp.

## 5. Ví dụ 2 — Ghi đè chính xác vùng đã chọn

File ban đầu:

~~~text
HELLO_____
0123456789   <- byte offsets
     ^
   offset 5
~~~

Ta ghi `WORLD` từ offset 5, không đổi một shared cursor nào.

Tạo `PatchAtPositionDemo.java`:

~~~java
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.concurrent.*;
import static java.nio.file.StandardOpenOption.*;

public class PatchAtPositionDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("pos-write-", ".txt");
        try {
            Files.writeString(
                    file, "HELLO_____", StandardCharsets.US_ASCII);

            try (AsynchronousFileChannel ch =
                    AsynchronousFileChannel.open(file, READ, WRITE)) {
                ByteBuffer block = ByteBuffer.wrap(
                        "WORLD".getBytes(StandardCharsets.US_ASCII));

                int n = ch.write(block, 5L)
                        .get(5, TimeUnit.SECONDS);

                System.out.println("written=" + n);
                System.out.println("size=" + ch.size());
                System.out.println("afterPatch=" +
                        Files.readString(
                                file, StandardCharsets.US_ASCII));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 PatchAtPositionDemo.java
java PatchAtPositionDemo
~~~

Stdout:

~~~text
written=5
size=10
afterPatch=HELLOWORLD
~~~

Kết quả đúng vì payload 5 byte ghi vào vùng 5..9 đã tồn tại. File không đổi size. Tuy nhiên **không được suy ra mỗi write luôn ghi đủ mọi byte còn trong ByteBuffer**; số `n` là số byte thực ghi, và production cần lặp tiếp nếu `block.hasRemaining()`.

## 6. Dùng một ByteBuffer cho nhiều I/O pending là sai

Khi gọi `read/write`, ByteBuffer vẫn thuộc về thao tác đó đến khi completion. Javadoc nêu rằng ByteBuffers **không an toàn khi được dùng cho nhiều I/O đồng thời**.

Không nên:

~~~java
ByteBuffer shared = ByteBuffer.allocate(4096);
Future<Integer> a = ch.read(shared, 0L);
Future<Integer> b = ch.read(shared, 4096L);
~~~

Đây là **đoạn minh họa sai về ownership**: hai thao tác cùng có thể thay đổi state/data của cùng một buffer.

Nên:

~~~java
ByteBuffer first = ByteBuffer.allocate(4096);
ByteBuffer second = ByteBuffer.allocate(4096);
Future<Integer> a = ch.read(first, 0L);
Future<Integer> b = ch.read(second, 4096L);
~~~

Đây là đoạn minh họa. Chỉ `flip()`/xử lý/tái sử dụng `first` sau khi `a` hoàn tất, và với `second` sau `b` hoàn tất.

**Cần lưu ý cả backing array:** Nếu `ByteBuffer.wrap(bytes)`, việc sửa trực tiếp mảng `bytes` trong lúc write đang pending cũng có thể làm thay đổi dữ liệu được ghi. Đừng nghĩ không đụng tới `buffer.position()` thì mọi thứ đã an toàn.

### 6.1. Con trỏ file không chung không có nghĩa không còn race

Giả sử hai thao tác ghi:

~~~text
A: offset 4, dài 4 -> byte 4,5,6,7
B: offset 6, dài 4 -> byte 6,7,8,9
                         ^ ^
                  vùng ghi chồng lấn
~~~

**Không có đảm bảo** B ghi sau A chỉ vì B được submit sau A. Javadoc không quy định thứ tự thực hiện outstanding I/O hoặc thứ tự gọi completion handlers. Với vùng chồng lấn, phải serialize hoặc thiết kế policy giải quyết xung đột; với các vùng rời nhau có thể tách tasks rõ ràng hơn.

## 7. Ví dụ 3 — Ba thao tác ghi vùng rời nhau

Tạo `IndependentBuffersDemo.java`:

~~~java
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import static java.nio.file.StandardOpenOption.*;

public class IndependentBuffersDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("slots-", ".txt");
        try {
            Files.writeString(
                    file, "............", StandardCharsets.US_ASCII);

            try (AsynchronousFileChannel ch =
                    AsynchronousFileChannel.open(file, READ, WRITE)) {
                ByteBuffer a = ByteBuffer.wrap(
                        "ABCD".getBytes(StandardCharsets.US_ASCII));
                ByteBuffer b = ByteBuffer.wrap(
                        "EFGH".getBytes(StandardCharsets.US_ASCII));
                ByteBuffer c = ByteBuffer.wrap(
                        "IJKL".getBytes(StandardCharsets.US_ASCII));

                Future<Integer> fa = ch.write(a, 0L);
                Future<Integer> fb = ch.write(b, 4L);
                Future<Integer> fc = ch.write(c, 8L);

                int total =
                        fa.get(5, TimeUnit.SECONDS)
                        + fb.get(5, TimeUnit.SECONDS)
                        + fc.get(5, TimeUnit.SECONDS);

                System.out.println("writesSubmitted=3");
                System.out.println("writtenBytes=" + total);
                System.out.println("result=" +
                        Files.readString(
                                file, StandardCharsets.US_ASCII));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 IndependentBuffersDemo.java
java IndependentBuffersDemo
~~~

Stdout đã kiểm chứng:

~~~text
writesSubmitted=3
writtenBytes=12
result=ABCDEFGHIJKL
~~~

Ba Future được tạo **trước khi** chờ. Mỗi buffer riêng và vùng file không chồng lấn. Chương trình chỉ đọc nội dung sau khi cả ba Future báo completion; **không dựa vào thứ tự hoàn thành**. Trong sản phẩm, vẫn phải kiểm tra từng write có ghi đủ bytes hay cần tiếp tục từ offset sau số byte đã ghi.

### 7.1. Cấp phát offset cho nhiều worker

Một hệ thống lưu record cố định có thể dùng layout:

~~~text
Header: 4096 byte
Record 0: offset 4096
Record 1: offset 8192
Record 2: offset 12288
...
Offset(record n) = headerSize + n * recordSize
~~~

Nếu data size lớn, tính `long` và chống overflow:

~~~java
long offset = Math.addExact(
        headerSize,
        Math.multiplyExact(recordIndex, recordSize));
~~~

Đây là đoạn minh họa trong một phương thức đã khai báo các biến dạng `long`. Đừng ép offset thành `int` hoặc cộng mà bỏ qua nguy cơ overflow.

Với record dài biến thiên, một allocator đồng bộ như `AtomicLong.getAndAdd(length)` có thể giúp cấp vùng **không chồng lấn** trong một JVM, nhưng vẫn cần thiết kế file header, publish, failure recovery, multi-process coordination và bounds validation phù hợp.

## 8. Future và CompletionHandler nhận kết quả ra sao?

Có hai cách:

**Future:**

~~~java
Future<Integer> future = ch.read(buffer, offset);
int transferred = future.get(5, TimeUnit.SECONDS);
~~~

**CompletionHandler:**

~~~java
ch.read(
        buffer,
        offset,
        attachment,
        new CompletionHandler<Integer, String>() {
            @Override
            public void completed(Integer n, String value) {
                // Đọc thành công n byte.
            }

            @Override
            public void failed(Throwable error, String value) {
                // Xử lý lỗi.
            }
        });
~~~

Các đoạn trên **không độc lập**, các biến đã được khai báo và cần import `java.nio.channels.*`/`java.util.concurrent.*`. Trong callback, `attachment` mang metadata của request, chẳng hạn ID record hoặc offset.

| Tiêu chí | Future | CompletionHandler |
| --- | --- | --- |
| Cách lấy kết quả | `future.get()` | `completed(Integer,A)` |
| Cách lấy lỗi | `ExecutionException.getCause()` | `failed(Throwable,A)` |
| Chặn caller thread? | `get()` có thể chặn | Initiation không cần chờ, callback chạy về sau |
| Timeout | `get(timeout,unit)` | Phải xây chính sách timeout/cancel riêng |
| Metadata theo request | Lưu ở cấu trúc khác | `attachment` |
| Buffer ownership | Giữ tới completion | Giữ tới completed/failed |

**Future.get timeout không hủy I/O.** Nếu get ném TimeoutException, tác vụ có thể còn pending; không tái sử dụng buffer ngay chỉ vì hết thời gian chờ.

## 9. Ví dụ 4 — CompletionHandler ghi tại offset 3

Tạo `HandlerWriteDemo.java`:

~~~java
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.concurrent.*;
import static java.nio.file.StandardOpenOption.*;

public class HandlerWriteDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("handler-write-", ".txt");
        try {
            Files.writeString(
                    file, "123-----", StandardCharsets.US_ASCII);

            CompletableFuture<String> done =
                    new CompletableFuture<>();

            try (AsynchronousFileChannel ch =
                    AsynchronousFileChannel.open(file, READ, WRITE)) {
                ByteBuffer src = ByteBuffer.wrap(
                        "XYZ".getBytes(StandardCharsets.US_ASCII));

                ch.write(
                        src,
                        3L,
                        "block1",
                        new CompletionHandler<Integer, String>() {
                    @Override
                    public void completed(
                            Integer n, String attachment) {
                        done.complete(attachment + ":" + n);
                    }

                    @Override
                    public void failed(
                            Throwable error, String attachment) {
                        done.completeExceptionally(error);
                    }
                });

                System.out.println("completion=" +
                        done.get(5, TimeUnit.SECONDS));
                System.out.println("text=" +
                        Files.readString(
                                file, StandardCharsets.US_ASCII));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 HandlerWriteDemo.java
java HandlerWriteDemo
~~~

Stdout:

~~~text
completion=block1:3
text=123XYZ--
~~~

`write(src,3L,"block1",handler)` ghi `XYZ` vào bytes 3..5. Handler nhận attachment `block1` và số byte đã ghi. `CompletableFuture` trong demo làm cầu nối tới main thread để kiểm chứng output, nên main vẫn chờ ở `done.get()`. Trong service thật, callback có thể cập nhật state hoặc gửi event tiếp theo mà không cần chặn thread gọi ban đầu.

**Cần có nhánh failed.** Bỏ qua `failed` làm ứng dụng mất tín hiệu khi I/O lỗi. Callback chạy trên thread pool liên kết với channel; không giả định nó luôn chạy trên thread gọi `write` hoặc chạy theo thứ tự submit.

## 10. Partial read, partial write và EOF

Một lời gọi read không cam kết fill toàn bộ ByteBuffer. Nếu yêu cầu 8 byte tại offset 100 nhưng chỉ đọc 3 byte, cần lần tiếp theo ở offset **103**, không phải đọc lại từ offset 100. Tương tự, sau write 3 byte, offset write tiếp theo phải tăng 3.

Quy trình tổng quát:

~~~text
long start = offset ban đầu
int transferredTotal = 0

while buffer.hasRemaining():
    n = read/write(buffer, start + transferredTotal).get()
    if read n == -1: EOF, dừng
    if n == 0: không tiến triển, retry/backoff hoặc báo lỗi
    if n > 0: transferredTotal += n
~~~

Đây là mô tả thuật toán, không phải code Java độc lập.

- `read` trả `-1` khi vị trí đọc **lớn hơn hoặc bằng file size** tại thời điểm đọc được thử, nếu buffer cần đọc dữ liệu.
- Một `read` có thể trả số byte dương ít hơn `remaining`.
- Một `write` có thể ghi ít hơn bytes còn lại.
- Nếu buffer còn chỗ nhưng trả `0` liên tục, không nên busy-spin mãi; cần chọn giới hạn retry/backoff hoặc báo lỗi.
- Khi file đang thay đổi đồng thời, không coi nhiều lần read là một snapshot transactional.
- Đối với fixed-length record, EOF trước đủ bytes có thể là tín hiệu file bị cắt/hỏng; quyết định tùy định dạng.

## 11. Ví dụ 5 — readFully và EOF

Tạo `ReadFullyDemo.java`:

~~~java
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.concurrent.*;
import static java.nio.file.StandardOpenOption.*;

public class ReadFullyDemo {
    static int readFully(
            AsynchronousFileChannel ch,
            ByteBuffer buf,
            long start) throws Exception {
        int total = 0;

        while (buf.hasRemaining()) {
            int n = ch.read(buf, start + total)
                    .get(5, TimeUnit.SECONDS);

            if (n < 0) {
                break;
            }
            if (n == 0) {
                throw new IllegalStateException("No read progress");
            }
            total += n;
        }
        return total;
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("read-fully-", ".txt");
        try {
            Files.writeString(
                    file, "0123456789", StandardCharsets.US_ASCII);

            try (AsynchronousFileChannel ch =
                    AsynchronousFileChannel.open(file, READ)) {
                ByteBuffer buf = ByteBuffer.allocate(5);
                int total = readFully(ch, buf, 3L);
                buf.flip();

                System.out.println("read=" + total);
                System.out.println("text=" +
                        StandardCharsets.US_ASCII.decode(buf));
                System.out.println("eof=" +
                        ch.read(ByteBuffer.allocate(2), 100L)
                                .get(5, TimeUnit.SECONDS));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ReadFullyDemo.java
java ReadFullyDemo
~~~

Stdout:

~~~text
read=5
text=34567
eof=-1
~~~

Đọc từ offset 3 cho năm byte `34567`. Đọc từ offset 100 của file 10 byte trả `-1`. Vòng lặp dùng `start+total` để không đọc trùng, xử lý `0` bằng lỗi có chủ đích nhằm tránh vòng vô hạn. Với production, nên có quy tắc retry/timeout/partial record rõ ràng.

## 12. Ví dụ 6 — writeFully với payload UTF-8

Tạo `WriteFullyUtf8Demo.java`:

~~~java
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.concurrent.*;
import static java.nio.file.StandardOpenOption.*;

public class WriteFullyUtf8Demo {
    static int writeFully(
            AsynchronousFileChannel ch,
            ByteBuffer data,
            long start) throws Exception {
        int total = 0;

        while (data.hasRemaining()) {
            int n = ch.write(data, start + total)
                    .get(5, TimeUnit.SECONDS);
            if (n <= 0) {
                throw new IllegalStateException("No write progress");
            }
            total += n;
        }
        return total;
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("write-utf8-", ".txt");
        try {
            Files.writeString(
                    file, "__.....__", StandardCharsets.UTF_8);

            try (AsynchronousFileChannel ch =
                    AsynchronousFileChannel.open(file, READ, WRITE)) {
                ByteBuffer data = ByteBuffer.wrap(
                        "Café".getBytes(StandardCharsets.UTF_8));

                int n = writeFully(ch, data, 2L);
                System.out.println("bytesWritten=" + n);
                System.out.println("bytesTotal=" + ch.size());
            }

            System.out.println("text=" +
                    Files.readString(file, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 WriteFullyUtf8Demo.java
java WriteFullyUtf8Demo
~~~

Stdout:

~~~text
bytesWritten=5
bytesTotal=9
text=__Café__
~~~

File ban đầu có 9 byte `__.....__`; payload `Café` có 5 byte UTF-8 và được ghi bắt đầu ở offset 2. `writeFully` cập nhật `total` theo số byte thực ghi. **Không tính offset bằng số ký tự Java**. Nếu chọn offset nằm giữa một code point đã mã hóa, bạn có thể làm hỏng dữ liệu UTF-8.

## 13. Ví dụ 7 — Offset âm và quyền read/write

Tạo `InvalidPositionDemo.java`:

~~~java
import java.nio.*;
import java.nio.channels.*;
import java.nio.file.*;
import static java.nio.file.StandardOpenOption.*;

public class InvalidPositionDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("invalid-pos-", ".bin");
        try {
            Files.write(file, new byte[]{10, 20, 30});

            try (AsynchronousFileChannel ch =
                    AsynchronousFileChannel.open(file, READ)) {
                boolean negativeRejected = false;
                boolean writeRejected = false;

                try {
                    ch.read(ByteBuffer.allocate(1), -1L);
                } catch (IllegalArgumentException ex) {
                    negativeRejected = true;
                }

                try {
                    ch.write(
                            ByteBuffer.wrap(new byte[]{1}), 0L);
                } catch (NonWritableChannelException ex) {
                    writeRejected = true;
                }

                System.out.println("negativeRejected=" +
                        negativeRejected);
                System.out.println("writeOnReadOnlyRejected=" +
                        writeRejected);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 InvalidPositionDemo.java
java InvalidPositionDemo
~~~

Stdout:

~~~text
negativeRejected=true
writeOnReadOnlyRejected=true
~~~

`read(...,-1L)` vi phạm yêu cầu offset không âm; `write` trên channel chỉ `READ` bị từ chối. Đây là lỗi **khi initiate** trong môi trường thử. Các lỗi I/O phát sinh *sau khi submit* thường cần được quan sát từ `future.get()` hoặc `handler.failed`, không phải tất cả đều ném ngay lúc gọi method.

## 14. Ví dụ 8 — FileChannel có current position, còn async channel thì không

Tạo `CompareFileChannelDemo.java`:

~~~java
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.concurrent.*;
import static java.nio.file.StandardOpenOption.*;

public class CompareFileChannelDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("compare-", ".txt");
        try {
            Files.writeString(
                    file, "ABCDEFGHIJ", StandardCharsets.US_ASCII);

            try (FileChannel sync = FileChannel.open(file, READ)) {
                ByteBuffer first = ByteBuffer.allocate(3);
                sync.read(first);
                System.out.println("afterRelativeReadPosition=" +
                        sync.position());

                ByteBuffer positional = ByteBuffer.allocate(3);
                sync.read(positional, 5L);
                positional.flip();
                System.out.println("fileChannelAt5=" +
                        StandardCharsets.US_ASCII.decode(positional));
                System.out.println("afterPositionalReadPosition=" +
                        sync.position());
            }

            try (AsynchronousFileChannel async =
                    AsynchronousFileChannel.open(file, READ)) {
                ByteBuffer at7 = ByteBuffer.allocate(3);
                ByteBuffer at0 = ByteBuffer.allocate(3);

                Future<Integer> f7 = async.read(at7, 7L);
                Future<Integer> f0 = async.read(at0, 0L);
                f7.get(5, TimeUnit.SECONDS);
                f0.get(5, TimeUnit.SECONDS);

                at7.flip();
                at0.flip();

                System.out.println("asyncAt7=" +
                        StandardCharsets.US_ASCII.decode(at7));
                System.out.println("asyncAt0=" +
                        StandardCharsets.US_ASCII.decode(at0));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 CompareFileChannelDemo.java
java CompareFileChannelDemo
~~~

Stdout:

~~~text
afterRelativeReadPosition=3
fileChannelAt5=FGH
afterPositionalReadPosition=3
asyncAt7=HIJ
asyncAt0=ABC
~~~

**Điều cần nhớ:**

- `FileChannel.read(buffer)` bắt đầu từ current position, sau đó position tăng lên 3.
- `FileChannel.read(buffer,5L)` là positional read, không làm thay đổi position 3.
- `AsynchronousFileChannel.read(buffer,7L)` và `read(buffer,0L)` độc lập về offset, không tồn tại shared cursor để sửa.
- FileChannel cũng có positional overload; sự khác nhau thực tế là cách báo completion và thiết kế không có current position ở async channel.

## 15. Ghi vượt cuối file và các byte khoảng trống

Theo Javadoc, khi write bắt đầu tại offset **lớn hơn file size** tại thời điểm thao tác, file tăng kích thước để chứa bytes được ghi. Tuy nhiên, **các byte giữa EOF cũ và vùng mới ghi có giá trị không được quy định** bởi hợp đồng API.

~~~text
File ban đầu: size=0
write "OK" tại offset 4
Byte index:   0 1 2 3 4 5
Nội dung:     ? ? ? ? O K
File mới: size=6

Các ký hiệu ? không có giá trị được đảm bảo bởi API.
~~~

Đừng giả định bốn byte đầu luôn là zero dù một filesystem cụ thể có thể làm vậy. Nếu định dạng đòi vùng trống xác định, ứng dụng phải ghi giá trị đó hoặc có một protocol quản lý vùng sparse rõ ràng.

## 16. Ví dụ 9 — File tăng kích thước do ghi ở offset xa

Tạo `GapGrowthDemo.java`:

~~~java
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.concurrent.*;
import static java.nio.file.StandardOpenOption.*;

public class GapGrowthDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("gap-", ".txt");
        try {
            try (AsynchronousFileChannel ch =
                    AsynchronousFileChannel.open(file, READ, WRITE)) {
                System.out.println("initialSize=" + ch.size());

                int n = ch.write(
                        ByteBuffer.wrap(
                                "OK".getBytes(StandardCharsets.US_ASCII)),
                        4L).get(5, TimeUnit.SECONDS);

                ByteBuffer out = ByteBuffer.allocate(2);
                int nr = ch.read(out, 4L)
                        .get(5, TimeUnit.SECONDS);
                out.flip();

                System.out.println("written=" + n);
                System.out.println("size=" + ch.size());
                System.out.println("readAt4=" +
                        StandardCharsets.US_ASCII.decode(out));
                System.out.println("readBytes=" + nr);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 GapGrowthDemo.java
java GapGrowthDemo
~~~

Stdout:

~~~text
initialSize=0
written=2
size=6
readAt4=OK
readBytes=2
~~~

Bài kiểm tra **không đọc/in bốn byte trống** vì Javadoc không cam kết giá trị của chúng. Nó kiểm chứng điều có thể dựa vào: số bytes được ghi, kích thước file mới và dữ liệu thật ở offset 4.

**Cảnh báo về append:** `size()` chỉ là số đo tại một thời điểm, không phải reservation. Nếu nhiều writers lấy size đồng thời và gọi write ở cùng size, chúng có thể ghi đè. Khi cần append đồng thời, dùng offset allocator và chính sách đồng bộ thích hợp.

## 17. size, truncate và force không phải những operation read/write bất đồng bộ

- `size()` cho kích thước file hiện tại tính bằng byte.
- `truncate(newSize)` giảm kích thước file nếu `newSize` nhỏ hơn size; nếu lớn hơn, file **không tự mở rộng**.
- `force(false)` yêu cầu đẩy cập nhật nội dung xuống thiết bị lưu trữ theo semantics, `force(true)` còn xét metadata. Mức bảo đảm có giới hạn với network filesystem và OS.
- Các method này **không có Future<Integer> kết quả** giống read/write.
- Nếu đang có writes pending, gọi `force` ngay không đảm bảo những writes đó đã xong; chờ Future/handler trước.

### 17.1. Ví dụ 10 — Rút file và kiểm tra EOF

Tạo `TruncateAndForceDemo.java`:

~~~java
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.concurrent.*;
import static java.nio.file.StandardOpenOption.*;

public class TruncateAndForceDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("truncate-", ".txt");
        try {
            Files.writeString(
                    file, "0123456789", StandardCharsets.US_ASCII);

            try (AsynchronousFileChannel ch =
                    AsynchronousFileChannel.open(file, READ, WRITE)) {
                ch.truncate(6L);
                System.out.println("sizeAfterShrink=" + ch.size());
                System.out.println("eofAt6=" +
                        ch.read(ByteBuffer.allocate(2), 6L)
                                .get(5, TimeUnit.SECONDS));

                ch.truncate(20L);
                System.out.println("sizeAfterLargeTruncate=" +
                        ch.size());
                ch.force(false);
            }

            System.out.println("content=" +
                    Files.readString(
                            file, StandardCharsets.US_ASCII));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 TruncateAndForceDemo.java
java TruncateAndForceDemo
~~~

Stdout:

~~~text
sizeAfterShrink=6
eofAt6=-1
sizeAfterLargeTruncate=6
content=012345
~~~

`truncate(6)` làm file từ 10 xuống 6 byte, nên read từ offset 6 trả EOF. `truncate(20)` **không** tăng file lên 20. `force(false)` được gọi sau khi thao tác I/O cần xét đã hoàn tất; output không cố đưa ra lời hứa tuyệt đối về khả năng sống sót sau mất điện.

## 18. Thread pool liên kết với channel

Javadoc mô tả AsynchronousFileChannel liên kết với thread pool để xử lý I/O events và dispatch completion handlers.

Bạn có thể để mặc định:

~~~java
AsynchronousFileChannel.open(file, StandardOpenOption.READ);
~~~

Hoặc truyền `ExecutorService`:

~~~java
AsynchronousFileChannel.open(
        file,
        Set.of(StandardOpenOption.READ),
        executor);
~~~

Các đoạn là minh họa trong method. Overload truyền executor không có nghĩa mỗi I/O bắt buộc tiêu thụ một thread riêng; chi tiết phụ thuộc provider. Javadoc khuyên executor tối thiểu hỗ trợ work queue không giới hạn và không chạy task ngay trên caller thread khi gọi `execute()`.

**Đừng shutdown executor khi channel còn mở**, hành vi khi làm vậy không được quy định. Nên đóng channel trước, sau đó shutdown executor khi không còn tác vụ cần xử lý.

## 19. Ví dụ 11 — Tự quản lý ExecutorService

Tạo `CustomExecutorDemo.java`:

~~~java
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import static java.nio.file.StandardOpenOption.*;

public class CustomExecutorDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("custom-exec-", ".txt");
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Files.writeString(
                    file, "POOL", StandardCharsets.US_ASCII);

            try (AsynchronousFileChannel ch =
                    AsynchronousFileChannel.open(
                            file, Set.of(READ), pool)) {
                ByteBuffer result = ByteBuffer.allocate(4);

                int n = ch.read(result, 0L)
                        .get(5, TimeUnit.SECONDS);
                result.flip();

                System.out.println("bytes=" + n);
                System.out.println("text=" +
                        StandardCharsets.US_ASCII.decode(result));
            }
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
            Files.deleteIfExists(file);
        }

        System.out.println("executorShutDown=" +
                pool.isShutdown());
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 CustomExecutorDemo.java
java CustomExecutorDemo
~~~

Stdout:

~~~text
bytes=4
text=POOL
executorShutDown=true
~~~

Ví dụ đóng channel trước khi shutdown executor. Cấu hình thread pool dùng để minh họa API, **không** phải lời khuyên rằng hai threads luôn là tối ưu. Hiệu năng tùy loại ổ đĩa, provider, queue depth, kích thước blocks và tải hệ thống.

## 20. Timeout, failure, cancellation và close

Với Future:

~~~java
Future<Integer> future = ch.read(buffer, position);
int n = future.get(5, TimeUnit.SECONDS);
~~~

Đây là đoạn trong phương thức, cần xử lý:

- `InterruptedException`: thread chờ bị interrupt; giữ/chuyển tín hiệu interrupt đúng.
- `ExecutionException`: tác vụ I/O thất bại; xem `getCause()`.
- `TimeoutException`: hết thời gian **chờ**, không đồng nghĩa I/O đã dừng.
- `CancellationException`: Future bị cancel, không nên suy luận mọi provider đã chấm dứt hoạt động I/O và buffer chắc chắn an toàn để tái sử dụng.
- Lỗi từ `read/write` **lúc initiate** như `IllegalArgumentException` hoặc `NonReadableChannelException` có thể ném ngay mà không có Future.

Với callback, cần xử lý `completed(n, attachment)` và `failed(error, attachment)`. Nếu callback bị lỗi, đừng bỏ quên đánh dấu task failed hoặc trả buffer về pool.

### 20.1. Đóng channel khi còn I/O

Javadoc quy định khi `close()` một channel, outstanding async operations hoàn tất với `AsynchronousCloseException`. Vì vậy dừng một hệ thống có thể theo trình tự:

1. Ngừng nhận request mới.
2. Chờ, hủy hoặc đánh dấu request pending theo chính sách.
3. Xử lý lỗi/timeout và giải phóng buffer đúng thời điểm.
4. Đóng channel.
5. Shutdown executor riêng nếu ứng dụng sở hữu nó.

Không đóng file rồi giả định mọi writes đang pending đã tự động thành công.

### 20.2. Không đảm bảo thứ tự I/O và callback

Nếu submit `write(A,0)` rồi `write(B,0)` ở cùng offset, kết quả cuối không được đảm bảo là B. Tương tự, callback thứ hai có thể được gọi trước callback thứ nhất. Muốn thứ tự tuần tự, hãy khởi phát tác vụ sau **khi tác vụ trước báo completion**, hoặc dùng một coordinator/queue có ràng buộc rõ.

### 20.3. FileLock không thay thế thiết kế records

Các phương thức `lock`/`tryLock` có thể hữu ích khi cần khóa file/vùng file, nhưng OS/provider có khác biệt và việc khóa không tự cho bạn transaction, undo, tính đúng của offset hay thứ tự callback. Với writer trong cùng JVM, allocator offset và giao thức publish record thường rõ hơn là kỳ vọng FileLock giải quyết mọi race.

## 21. Thiết kế ứng dụng thực tế với các khối dữ liệu

Một ứng dụng tốt có thể dùng mô hình:

~~~text
Record layout
    header: version, length, checksum
    offset: long, được cấp bởi allocator
    payload: byte[]/ByteBuffer thuộc một request
    completion: Future hoặc handler
    publish: chỉ khi dữ liệu cần thiết hoàn tất
~~~

Các bước:

1. Xác định định dạng record và byte length.
2. Cấp một offset không chồng lấn, kiểm tra overflow và giới hạn file.
3. Tạo buffer riêng cho task; với text thì mã hóa UTF-8 trước khi tính length.
4. Khởi phát `write(buffer,offset)`.
5. Nếu Future/handler báo partial transfer, tiếp tục từ `offset+totalWritten`.
6. Khi tất cả writes cần thiết thành công, gọi `force` nếu yêu cầu durability.
7. Chỉ công bố record “ready” sau khi hoàn tất các điều kiện của giao thức.
8. Đọc theo offset rõ ràng; nếu file đổi đồng thời, có version/checksum hoặc snapshot strategy.
9. Giới hạn số requests pending để tránh tiêu thụ quá nhiều memory/threads.
10. Theo dõi latency, throughput, timeouts, errors và thời gian flush.

**AsynchronousFileChannel không tự cung cấp transaction nhiều writes.** Nếu process crash sau khi ghi header nhưng trước payload, file có thể ở trạng thái dở dang. Một định dạng có length/checksum/commit marker hoặc xây dựng file tạm rồi publish là quyết định nghiệp vụ riêng. Khi yêu cầu ACID phức tạp, database có thể phù hợp hơn.

### 21.1. Không mặc định async luôn nhanh hơn

Một số OS/providers có thể triển khai async file I/O bằng thread pool thực hiện thao tác chặn bên dưới; API không hứa kernel-level async I/O trên mọi nền tảng. Với tác vụ nhỏ, overhead scheduling có thể vượt lợi ích. Nếu code gọi `get()` ngay sau mỗi write, caller vẫn chờ, nên ưu điểm concurrency có thể rất ít.

So sánh thật với `FileChannel` trên workload của bạn, đo throughput, latency P95/P99, CPU, memory, queue depth và độ bền dữ liệu.

## 22. Bảo mật và tính nhất quán

Việc truyền offset rõ ràng không tự giải quyết:

- Path không tin cậy, symbolic link trỏ ngoài root và quyền filesystem.
- File bị tiến trình khác delete/move/truncate trong lúc I/O.
- Ghi chồng lấn giữa hai requests.
- Vượt giới hạn `long`/file format khi tính offset.
- Tái sử dụng shared ByteBuffer/backing array trước completion.
- Partial read/write, timeout và close khi còn pending.
- Dữ liệu đã được force bền vững hay chưa.
- File đang thay đổi và read không tạo snapshot nhất quán.

Với file từ nguồn không tin cậy, cần giới hạn path trong thư mục được phép, kiểm soát permission/ownership và cân nhắc symlink/TOCTOU. `Files.exists(path)` trước lúc mở channel không khóa filesystem khỏi thay đổi; việc đọc từ channel không xác minh format/checksum của bytes.

## 23. Bảng lỗi thường gặp

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Tưởng async channel có current position | Chọn sai API hoặc cố seek | Luôn truyền explicit offset |
| Đặt offset theo ký tự UTF-8 | Ghi vào giữa code point | Tính encoded bytes |
| Dùng chung ByteBuffer cho concurrent I/O | Data/position race | Mỗi task một buffer |
| Thay buffer ngay sau submit | I/O có thể chưa đọc xong buffer | Đợi completion |
| Cho rằng read luôn fill buffer | Record thiếu bytes | Lặp theo số bytes thực đọc |
| Cho rằng write luôn ghi đủ | Thiếu data | Lặp từ offset cộng dồn |
| Không xử lý `-1` | EOF bị hiểu nhầm | Dừng/đánh dấu record thiếu |
| Không xử lý `0` | Busy-loop không tiến triển | Retry/backoff/abort |
| Submit overlapping writes | Thứ tự không quy định | Serialize hoặc tránh overlap |
| Lấy `size()` để append đồng thời | Nhiều tasks cùng offset | Offset allocator |
| Tin thứ tự callbacks là thứ tự submit | Logic order sai | Phối hợp completion |
| Gọi `get()` ngay rồi tưởng không blocking | Caller vẫn có thể chờ | Callback hoặc work scheduling |
| Timeout rồi tái dùng buffer | Pending I/O vẫn có thể chạy | Cancel/cleanup policy |
| Đóng channel trước pending operations | AsynchronousCloseException | Quản lý lifecycle |
| Shutdown executor khi channel còn mở | Behavior unspecified | Channel đóng trước |
| Ghi beyond EOF rồi đọc gap như zero | API không cam kết byte gap | Điền rõ dữ liệu hoặc dùng layout |
| Truncate lên size lớn rồi mong file grow | Không mở rộng | Ghi dữ liệu ở offset cần |
| Force trước Future completion | Chưa đảm bảo force writes pending | Chờ kết quả rồi force |
| Mở chỉ READ rồi write | NonWritableChannelException | Chọn options phù hợp |
| Offset âm | IllegalArgumentException | Validate ≥ 0 |
| Đo performance bằng ví dụ quá nhỏ | Kết luận sai | Benchmark workload thực |

## 24. Checklist trước khi triển khai

1. Nhiệm vụ thực sự cần random access hoặc nhiều I/O outstanding?
2. Mỗi read/write đã có offset byte rõ ràng?
3. Đã chống offset âm và overflow khi tính layout?
4. Đã chọn quyền `READ/WRITE/CREATE/TRUNCATE_EXISTING` phù hợp?
5. Có phân biệt file offset và Buffer.position?
6. Sau read có dùng `flip()` trước khi parse?
7. Buffer có ownership riêng và không được sửa trước completion?
8. Đã xử lý partial read/write và EOF?
9. Có giới hạn retry khi result bằng 0?
10. Có chuẩn bị chiến lược xử lý UTF-8 và binary records?
11. Mọi concurrent writes có vùng không chồng lấn hoặc synchronization?
12. Ghi nối đồng thời có offset allocator riêng?
13. Có phân biệt Future.get blocking với callback?
14. Có xử lý `ExecutionException` và `TimeoutException` đúng?
15. Có xem `CompletionHandler.failed` như một nhánh bắt buộc?
16. Có chờ completion trước khi force/publish?
17. Có hiểu size/truncate là synchronous methods?
18. Có đóng channel sau khi xử lý pending operations?
19. Nếu cung cấp executor, có đóng channel trước khi shutdown?
20. Có kiểm thử lỗi quyền, offset âm, EOF, partial I/O, close khi pending?
21. Có kiểm tra path/symlink, quyền, dữ liệu và checksum theo chính sách?
22. Có đo benchmark thật thay vì mặc định async nhanh hơn?

## 25. Câu hỏi tự kiểm tra

**1.** `AsynchronousFileChannel` có con trỏ current position không?  
**Đáp án:** Không; mỗi read/write có offset tường minh.

**2.** `read(buf,5L)` đọc từ đâu?  
**Đáp án:** Từ byte offset 5 tính từ đầu file.

**3.** Buffer.position có phải file offset không?  
**Đáp án:** Không, đó là vị trí trong ByteBuffer.

**4.** `Future<Integer>.get()` trả gì?  
**Đáp án:** Số bytes thực chuyển, hoặc -1 khi read gặp EOF.

**5.** Future.get có thể chặn thread không?  
**Đáp án:** Có khi operation chưa xong.

**6.** Một write luôn ghi đầy payload không?  
**Đáp án:** Không; kiểm tra bytes thực ghi và lặp.

**7.** Có thể dùng cùng ByteBuffer cho hai pending operations không?  
**Đáp án:** Không an toàn.

**8.** Ghi chồng lấn có được đảm bảo theo thứ tự submit không?  
**Đáp án:** Không.

**9.** Chuỗi `Café` UTF-8 dài mấy byte?  
**Đáp án:** Năm byte.

**10.** Ghi hai byte tại offset 4 khi file rỗng làm size bao nhiêu?  
**Đáp án:** Sáu byte; gap bytes không được API quy định.

**11.** Ghi tại offset lớn hơn EOF có tự zero-fill theo contract không?  
**Đáp án:** Không được mặc định.

**12.** FileChannel có positional overload không?  
**Đáp án:** Có; read/write(buffer,position) không đổi current position.

**13.** Vì sao async channel khác?  
**Đáp án:** Nó không có current file position, và read/write báo completion qua Future/handler.

**14.** `truncate(20L)` có làm file 6 byte dài lên 20 không?  
**Đáp án:** Không.

**15.** Timeout ở Future.get có đồng nghĩa operation bị hủy?  
**Đáp án:** Không.

**16.** Callback.failed dùng làm gì?  
**Đáp án:** Nhận lỗi và hoàn tất nhánh xử lý thất bại.

**17.** Nên gọi force trước hay sau writes hoàn tất?  
**Đáp án:** Sau các Future/callback liên quan hoàn tất thành công.

**18.** Có thể shutdown executor khi channel vẫn mở không?  
**Đáp án:** Không nên; Javadoc không quy định hành vi ấy.

**19.** Nhiều producers dùng size()+write có an toàn để append?  
**Đáp án:** Không, có race; cần allocator/coordination.

**20.** AsynchronousFileChannel luôn nhanh hơn FileChannel?  
**Đáp án:** Không; benchmark theo workloads.

## 26. Tài liệu chính thức

- [Oracle Java SE 26 — AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): không có current position, explicit offset, Future, CompletionHandler, thứ tự concurrent operations, ByteBuffer ownership, file growth, size/truncate/force và executor.
- [Oracle Java SE 26 — FileChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/FileChannel.html): current position và positional overload không đổi current position.
- [Oracle Java SE 26 — CompletionHandler](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/CompletionHandler.html): completed/failed và attachment.
- [Oracle Java SE 26 — ByteBuffer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/ByteBuffer.html): position, limit, remaining, flip, clear.
- [Oracle Java SE 26 — Future](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html): get, timeout, cancellation.
- [Oracle Java SE 26 — CompletableFuture](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html): phối hợp completion.
- [Oracle Java SE 26 — StandardOpenOption](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/StandardOpenOption.html): READ/WRITE/CREATE/TRUNCATE_EXISTING/SYNC.
- [Oracle Java SE 26 — AsynchronousCloseException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/AsynchronousCloseException.html): đóng channel khi I/O chưa hoàn tất.
- [Oracle Java SE 26 — FileLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/FileLock.html): khóa file/vùng.
- [Oracle Java SE 26 — ExecutorService](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý thread pool.
- [Oracle Java SE 26 — Files](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): tạo/đọc fixture và quyền/path.
- [Oracle Java SE 17 — AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): đối chiếu API Java 17 dùng cho chương trình.
- [Oracle Java SE 7 — AsynchronousFileChannel](https://docs.oracle.com/javase/7/docs/api/java/nio/channels/AsynchronousFileChannel.html): xác nhận API bắt đầu từ Java 7.

**Ghi nhớ:** `AsynchronousFileChannel` không dùng con trỏ file chung. Mỗi read/write nhận **byte offset riêng**. Nhờ vậy, nhiều tác vụ có thể truy cập các vùng đã phân công mà không phải thay shared current position. Nhưng tính đúng đắn vẫn đòi hỏi buffer riêng, kiểm soát partial I/O, EOF, overlap, completion ordering, timeout, close, quyền file và dữ liệu đã ghi bền vững.