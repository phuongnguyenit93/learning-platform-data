# AsynchronousFileChannel và vị trí thao tác tường minh trong Java NIO.2

## 1. Mục tiêu và ý tưởng cốt lõi

`java.nio.channels.AsynchronousFileChannel` là API đọc/ghi tệp theo mô hình **bất đồng bộ** trong Java NIO.2. Thay vì bắt buộc luồng gọi đứng chờ cho đến khi đọc/ghi xong, ứng dụng có thể **khởi tạo một thao tác I/O**, nhận lại đối tượng `Future` hoặc cung cấp `CompletionHandler` để xử lý khi tác vụ hoàn tất.

Đặc điểm quyết định của API này: **mỗi lần đọc/ghi phải truyền vị trí tệp tường minh** (`long position`).

```java
Future<Integer> pendingRead = channel.read(destination, 128L);
Future<Integer> pendingWrite = channel.write(source, 512L);
```

Hai lệnh trên là ví dụ minh họa với channel đã mở; chúng trả ngay một `Future<Integer>` đại diện cho kết quả sẽ có. Số nguyên kết quả là **số byte thực sự được xử lý**, không phải offset mới. Đọc có thể trả `-1` khi gặp EOF.

Không có API `channel.position()` hay `channel.read(buffer)` không đối số offset như `FileChannel`. Vì vậy, mỗi tác vụ phải tự biết **mình đang làm việc ở vị trí nào trong tệp**. Khi một lời gọi chỉ đọc/ghi được một phần dữ liệu, ứng dụng phải tự tăng offset và gửi thao tác tiếp theo.

Bài này giúp bạn:

1. Phân biệt I/O bất đồng bộ với I/O đồng bộ và non-blocking channel.
2. Mở `AsynchronousFileChannel` đúng quyền và quản lý tài nguyên.
3. Dùng hai cách nhận kết quả: **`Future`** và **`CompletionHandler`**.
4. Tính offset chính xác, xử lý partial read/write, EOF và `ByteBuffer`.
5. Hiểu rủi ro khi chia sẻ buffer, ghi đồng thời, lỗi, đóng channel và hủy Future.
6. Áp dụng một chương trình Java 17+ độc lập có thể biên dịch/chạy.

## 2. Bất đồng bộ không đồng nghĩa tệp tự có con trỏ tiến lên

Hãy xem tệp có mười byte ASCII:

```text
File offset:  0 1 2 3 4 5 6 7 8 9 10
Content:      A B C D E F G H I J |EOF|
```

Nếu muốn đọc bốn byte từ offset 3:

```java
ByteBuffer part = ByteBuffer.allocate(4);
Future<Integer> request = channel.read(part, 3L);
int count = request.get();
```

Khi yêu cầu đã hoàn tất và đọc được đủ bốn byte, `part` chứa `DEFG`. Nhưng **channel không có một current position chung đã được chuyển từ 3 lên 7**. Nếu muốn đọc tiếp, hãy chỉ định **offset 7** ở lời gọi tiếp theo:

```java
ByteBuffer next = ByteBuffer.allocate(3);
Future<Integer> second = channel.read(next, 7L);
```

Điểm khác biệt với `FileChannel.read(buffer)` là thao tác đồng bộ tương đối có thể tự tiến `FileChannel.position()`. `AsynchronousFileChannel` luôn nhận offset cho mỗi `read/write`. Đây là thiết kế thuận lợi khi các tác vụ độc lập muốn truy cập những vùng tệp khác nhau mà không tranh chấp một con trỏ file chung.

### Mô hình tư duy

```text
Thread ứng dụng                    Hệ thống/thực thi I/O

read(dst, offset=3) ----------->  xử lý đọc bắt đầu từ byte 3
   |
   +--> Future<Integer>           [có thể chưa hoàn tất]
   |
   +--> làm công việc khác
   |
future.get() ----------------->  chờ nếu chưa xong
   |
   +--> nhận số byte đã đọc
   +--> cập nhật offset của ứng dụng nếu cần đọc tiếp
```

API bất đồng bộ **không cam kết rằng mọi hệ điều hành đều cung cấp native async disk I/O**: provider có thể sử dụng thread pool và các thao tác file đồng bộ ở phía dưới. Tính bất đồng bộ ở đây nói về **giao diện khởi tạo và nhận completion**, không phải lời bảo đảm tăng hiệu năng trong mọi tình huống.

## 3. So sánh với FileChannel và SocketChannel

| Tiêu chí | `FileChannel` | `AsynchronousFileChannel` | `SocketChannel` non-blocking |
|---|---|---|---|
| Nguồn I/O | Tệp | Tệp | TCP socket |
| Mô hình API | Đọc/ghi đồng bộ theo cách dùng thông thường | Khởi tạo thao tác, nhận `Future` hoặc callback | Gọi `read/write`, sẵn sàng xử lý theo Selector |
| Current file position | Có `position()`/`position(long)` | **Không có** current file position kiểu này | Không phải file offset |
| Đọc/ghi theo offset | Có `read/write(ByteBuffer,long)` | **Bắt buộc** cung cấp `position` trong các lệnh read/write | Không áp dụng offset tệp |
| Thời điểm nhận kết quả | Return khi lời gọi đọc/ghi hoàn thành | Future/callback báo completion | Lời gọi trả ngay lượng byte xử lý nếu non-blocking |
| `Selector` | Không phải selectable channel | **Không đăng ký Selector** | Có thể đăng ký Selector |
| Buffer | `ByteBuffer` | `ByteBuffer`, phải giữ ổn định trong khi pending | `ByteBuffer` |
| Đặc điểm cần lưu ý | Có current position dùng chung ở relative I/O | Offset tường minh; completion order có thể khác thứ tự khởi tạo | Readiness không phải completion của một tác vụ riêng |

**Không gọi `configureBlocking(false)` trên `AsynchronousFileChannel`**: nó không hoạt động theo mô hình `SelectableChannel`. Muốn nhận completion, dùng `Future` hoặc `CompletionHandler`. `Selector` là công cụ readiness phù hợp cho một số network channels, không phải mọi API có chữ “channel”.

## 4. Cách mở AsynchronousFileChannel

### Mở đơn giản

```java
import java.nio.channels.AsynchronousFileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path path = Path.of("data.bin");

try (AsynchronousFileChannel channel = AsynchronousFileChannel.open(
        path,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE,
        StandardOpenOption.CREATE)) {
    // Khởi tạo I/O và chờ/nhận kết quả trước khi đóng.
}
```

Đây là **đoạn code minh họa**; cần đặt trong class/method để chạy. Các option phổ biến:

- `READ`: cho phép đọc.
- `WRITE`: cho phép ghi.
- `CREATE`: tạo tệp nếu chưa tồn tại khi mở để ghi.
- `CREATE_NEW`: chỉ tạo mới; lỗi nếu tệp đã tồn tại.
- `TRUNCATE_EXISTING`: khi mở cho ghi, cắt tệp cũ về rỗng.
- `DELETE_ON_CLOSE`: cơ chế xóa theo vòng đời mở/đóng, phải hiểu quyền và tương tác với hệ thống tệp trước khi dùng.

**`APPEND` không hợp lệ đối với `AsynchronousFileChannel`** theo hợp đồng mở channel. API này nhận offset rõ ràng trong từng thao tác; nếu cần append an toàn nhiều writer, đừng dùng `size() + write` như một bảo đảm append nguyên tử.

### Mở với ExecutorService

`AsynchronousFileChannel.open(Path, Set<? extends OpenOption>, ExecutorService, FileAttribute<?>...)` cho phép cấp thread pool tùy chọn. Mẫu code (minh họa):

```java
ExecutorService executor = Executors.newFixedThreadPool(4);
try {
    try (AsynchronousFileChannel channel =
            AsynchronousFileChannel.open(
                    path,
                    Set.of(StandardOpenOption.READ, StandardOpenOption.WRITE),
                    executor)) {
        // Khởi tạo I/O và đảm bảo mọi pending operation đã kết thúc.
    }
} finally {
    executor.shutdown();
}
```

Cần import `ExecutorService`, `Executors`, `Set`, `AsynchronousFileChannel` và `StandardOpenOption`. Ở overload này, thread pool do caller cung cấp; **caller chịu trách nhiệm vòng đời ExecutorService** và phải phối hợp shutdown với tác vụ/callback chưa hoàn tất. Không shutdown quá sớm khi vẫn đang gửi thao tác mới hoặc chờ callback xử lý kết quả.

Thread pool có thể ảnh hưởng throughput/latency. Không suy ra 4 thread luôn là tối ưu; cần đo trên filesystem, loại I/O và mức concurrency thực tế. `AsynchronousFileChannel.open` không tự biến mọi ổ đĩa thành nền tảng I/O không block thật sự.

## 5. Cách 1 — Nhận kết quả bằng Future<Integer>

API đơn giản:

```java
Future<Integer> future = channel.read(dst, fileOffset);
int n = future.get();
```

`future.get()`:

- **Chờ** nếu thao tác chưa hoàn tất.
- Trả số byte đã đọc khi thành công, `-1` nếu EOF.
- Có thể ném `InterruptedException` khi thread đang chờ bị interrupt.
- Có thể ném `ExecutionException`, với nguyên nhân thật nằm trong `getCause()` khi thao tác I/O thất bại.
- Một Future đã được hoàn tất có thể lấy kết quả qua `get` nhiều lần mà không khởi tạo lại I/O.

Ghi tương tự:

```java
ByteBuffer src = StandardCharsets.UTF_8.encode("hello");
Future<Integer> pending = channel.write(src, 0L);
int written = pending.get();
```

Lời gọi `write` chỉ đưa byte có trong **vùng remaining của buffer** tại thời điểm thực thi thao tác. Không được tùy tiện `clear`, `flip`, `put` hoặc dùng cùng buffer cho một I/O khác trong lúc thao tác còn pending.

**Điểm thiết kế:** nếu gọi `future.get()` ngay sau mỗi lần `read/write`, thread thực tế vẫn đứng chờ. Code vẫn đúng và hữu ích để hiểu API hoặc viết helper đọc/ghi đủ byte, nhưng không tận dụng hết khả năng chồng lấp I/O với công việc khác. Muốn có concurrency, có thể phát động các thao tác độc lập, xử lý việc khác, rồi kiểm tra các Future/callback khi hoàn tất.

### Timeout khi chờ Future

```java
int n = future.get(3, TimeUnit.SECONDS);
```

Đây là ví dụ cần `TimeUnit` và xử lý `TimeoutException`, `InterruptedException`, `ExecutionException`. Timeout của `get` chỉ giới hạn **thời gian thread chờ**; nó **không mặc định chứng minh I/O trong hệ thống đã bị hủy**. Ngay cả `future.cancel(...)` cũng không nên được hiểu là một cam kết portable rằng mọi I/O đã ngừng và buffer có thể bị thay đổi tùy ý ngay tức thì. Hãy quản lý vòng đời pending operation theo hợp đồng implementation và bảo vệ buffer cho tới trạng thái an toàn.

## 6. Đọc/ghi đúng N byte: offset phải tự tăng

Một lần `read(dst, offset)` hoặc `write(src, offset)` **có thể trả ít byte hơn `remaining()`**. Vì không có current file position để tự tiến, helper phải quản lý `long fileOffset`.

### Đọc đủ một vùng

```java
static void readFully(
        AsynchronousFileChannel channel,
        ByteBuffer target,
        long startOffset
) throws Exception {
    long offset = startOffset;

    while (target.hasRemaining()) {
        Future<Integer> pending = channel.read(target, offset);
        int n = pending.get();

        if (n < 0) {
            throw new EOFException("Unexpected EOF at offset " + offset);
        }
        if (n == 0) {
            throw new IOException("Read made no progress");
        }
        offset += n;
    }
}
```

**Đây là phương thức minh họa**, với import `EOFException`, `IOException`, `AsynchronousFileChannel`, `ByteBuffer`, `Future`. Nó chờ kết thúc từng request trước khi tái sử dụng buffer. Việc ném lỗi ở `n == 0` tránh vòng lặp vô hạn; hệ thống cần chính sách retry/backoff riêng có thể dùng chiến lược khác.

### Ghi đủ một vùng

```java
static void writeFully(
        AsynchronousFileChannel channel,
        ByteBuffer source,
        long startOffset
) throws Exception {
    long offset = startOffset;

    while (source.hasRemaining()) {
        Future<Integer> pending = channel.write(source, offset);
        int n = pending.get();

        if (n <= 0) {
            throw new IOException("Write made no progress");
        }
        offset += n;
    }
}
```

Mỗi lần `write` hoàn tất, vị trí **buffer** tăng theo số byte thật sự xử lý, và **biến offset của ứng dụng** phải tăng tương ứng. Nếu viết vòng lặp nhưng luôn gọi `channel.write(source, startOffset)` mà không cộng `n`, lần ghi sau có thể **ghi đè chính các byte của lần ghi trước**.

### Tại sao cần offset kiểu long?

Tệp có thể lớn hơn 2 GiB, vượt giới hạn `int`. Khi tính vị trí bản ghi cố định:

```java
long offset = Math.addExact(
        headerSize,
        Math.multiplyExact((long) recordIndex, recordSize)
);
```

Đây là đoạn minh họa, biến cần khai báo với kiểu thích hợp. `Math.multiplyExact`/`addExact` giúp phát hiện tràn số khi offset tính từ input, thay vì biến thành offset sai. Kiểm tra `offset >= 0` và offset + kích thước thao tác không vượt giới hạn format cho phép.

## 7. Ví dụ Java 17+ hoàn chỉnh: các vị trí tường minh

Ví dụ sau:

1. Tạo tệp tạm.
2. Ghi mười byte ASCII `ABCDEFGHIJ` bắt đầu từ offset 0.
3. Đọc ba byte từ offset 0 thành `ABC`.
4. Đọc bốn byte từ offset 3 thành `DEFG`.
5. Ghi đè byte tại offset 4 bằng `XY`, làm `EF` thành `XY`.
6. Đọc lại toàn bộ, nhận `ABCDXYGHIJ`.
7. Mọi helper dùng `Future`, chờ completion và tự tăng offset.

Lưu đúng tên tệp **`AsyncFilePositionDemo.java`**:

```java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.Future;

public class AsyncFilePositionDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("async-position-", ".bin");

        try {
            try (AsynchronousFileChannel channel = AsynchronousFileChannel.open(
                    file,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {

                ByteBuffer initial = StandardCharsets.US_ASCII.encode(
                        "ABCDEFGHIJ");
                writeFully(channel, initial, 0L);
                System.out.println("Size: " + channel.size());

                ByteBuffer first = ByteBuffer.allocate(3);
                readFully(channel, first, 0L);
                first.flip();
                System.out.println("First: "
                        + StandardCharsets.US_ASCII.decode(first));

                ByteBuffer middle = ByteBuffer.allocate(4);
                readFully(channel, middle, 3L);
                middle.flip();
                System.out.println("Middle: "
                        + StandardCharsets.US_ASCII.decode(middle));

                ByteBuffer replacement = StandardCharsets.US_ASCII.encode("XY");
                writeFully(channel, replacement, 4L);

                ByteBuffer whole = ByteBuffer.allocate(10);
                readFully(channel, whole, 0L);
                whole.flip();
                System.out.println("Final: "
                        + StandardCharsets.US_ASCII.decode(whole));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }

    private static void readFully(
            AsynchronousFileChannel channel,
            ByteBuffer target,
            long startOffset
    ) throws Exception {
        long offset = startOffset;

        while (target.hasRemaining()) {
            Future<Integer> future = channel.read(target, offset);
            int n = future.get();
            if (n == -1) {
                throw new EOFException("Unexpected EOF at " + offset);
            }
            if (n == 0) {
                throw new IOException("Read made no progress");
            }
            offset += n;
        }
    }

    private static void writeFully(
            AsynchronousFileChannel channel,
            ByteBuffer source,
            long startOffset
    ) throws Exception {
        long offset = startOffset;

        while (source.hasRemaining()) {
            Future<Integer> future = channel.write(source, offset);
            int n = future.get();
            if (n <= 0) {
                throw new IOException("Write made no progress");
            }
            offset += n;
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa mã:

```bash
javac AsyncFilePositionDemo.java
java AsyncFilePositionDemo
```

**Stdout khi filesystem cho phép tạo, đọc, ghi và xóa tệp tạm:**

```text
Size: 10
First: ABC
Middle: DEFG
Final: ABCDXYGHIJ
```

Đây là kết quả dự kiến chính xác khi mọi thao tác hoàn tất thành công. Thứ tự dòng in là xác định vì mỗi helper `get()` chờ thao tác của mình kết thúc trước khi chuyển sang bước tiếp.

**Giải thích từng bước:**

- Ghi `ABCDEFGHIJ` tại offset 0 làm kích thước tệp bằng 10.
- `readFully(...,0L)` đọc `ABC`; không có current position bị dịch sang 3 trên channel.
- `readFully(...,3L)` đọc `DEFG` độc lập với lần đọc trước.
- `writeFully(...,4L)` ghi `XY` tại hai vị trí 4, 5, thay `EF` nhưng không chèn byte; độ dài vẫn 10.
- `readFully(...,0L)` đọc lại từ đầu mà không cần “seek về 0” hay reopen.
- `ByteBuffer.flip()` đặt buffer vào trạng thái đọc phần byte vừa nhận trước khi giải mã ASCII.
- Dù API dùng Future, helper này **đọc/ghi tuần tự theo từng bước vì chờ `get`**. Mục tiêu là làm rõ offset và tính đúng đắn; phần chạy song song là chủ đề kiến trúc bổ sung.

## 8. Cách 2 — CompletionHandler: callback khi I/O hoàn tất

Thay vì trả `Future` và chờ `get()`, `AsynchronousFileChannel` có overload nhận `attachment` và `CompletionHandler`:

```java
channel.read(buffer, offset, attachment, handler);
channel.write(buffer, offset, attachment, handler);
```

Với read:

```java
channel.read(
        destination,
        100L,
        "record-25",
        new CompletionHandler<Integer, String>() {
            @Override
            public void completed(Integer bytesRead, String recordId) {
                System.out.println(
                        "Completed " + recordId + ": " + bytesRead);
            }

            @Override
            public void failed(Throwable error, String recordId) {
                System.err.println(
                        "Failed " + recordId + ": " + error);
            }
        });
```

Đây là **đoạn minh họa trong một method**, cần import `CompletionHandler`, khai báo `channel` và `destination`. `attachment` là dữ liệu ứng dụng tự truyền (ở đây là String `"record-25"`), giúp callback biết request nào hoàn tất. Attachment có thể là object chứa offset, buffer, request ID, deadline hoặc state; không tự động gắn với dữ liệu lưu trong tệp.

Khác biệt quan trọng:

- Callback `completed(result, attachment)` nhận số byte đã xử lý, không nhận luôn `ByteBuffer` trừ khi ứng dụng giữ reference (ví dụ qua attachment).
- Callback `failed(exception, attachment)` nhận lỗi I/O bất đồng bộ.
- Callback có thể chạy trên thread khác với thread gọi `read/write`.
- Thứ tự callback của nhiều yêu cầu độc lập **không được giả định trùng với thứ tự khởi tạo**.
- Nếu lần read chỉ xử lý một phần, callback phải gửi read mới với **offset + bytesRead** và buffer còn remaining, hoặc chuyển giao phần còn thiếu cho một bộ điều phối.
- Callback phải xử lý ngoại lệ một cách có kiểm soát. Một exception không được bắt ngay trong callback không nên được coi là tự động được gửi tới thread khởi tạo như `Future.get()`.

### Callback đọc đủ vùng: bản minh họa có state

```java
record ReadState(ByteBuffer buffer, long nextOffset) {}

static void readNext(
        AsynchronousFileChannel channel,
        ByteBuffer target,
        long offset,
        CompletionHandler<Integer, Long> handler
) {
    channel.read(target, offset, offset, handler);
}
```

Đoạn này minh họa cách dùng **offset làm attachment**; cần khai báo trong class, import các kiểu và sử dụng `record` chỉ như một ví dụ mô hình hóa state. Khi callback thấy `n > 0`, lần đọc tiếp có thể gọi `channel.read(target, oldOffset + n, oldOffset + n, this)`. Nếu `n == -1` trước khi đủ byte thì lỗi EOF. Nếu `n == 0`, nên có chính sách retry/backoff có giới hạn. Một implementation thực tế cần promise/future hoặc handler cuối để báo “toàn bộ record đã đọc đủ”; không được đánh dấu hoàn tất chỉ vì một lần callback thành công.

**Không trộn code Future và callback cho cùng một lần I/O.** Hai overload tạo hai cách nhận kết quả; chọn một mô hình quản lý completion rõ ràng cho mỗi request.

## 9. ByteBuffer khi thao tác còn pending

Đây là điểm rất dễ phát sinh lỗi trong I/O bất đồng bộ.

`AsynchronousFileChannel.read` ghi dữ liệu vào `ByteBuffer`; `write` đọc dữ liệu từ buffer. Trong thời gian I/O chưa hoàn tất:

- Không nên thay `position`, `limit` hay nội dung của buffer.
- Không khởi tạo thao tác read/write khác sử dụng **cùng một buffer** khi chưa đảm bảo thao tác trước đã xong.
- Không decode/đọc dữ liệu vừa nhận trước completion.
- Không tái sử dụng hoặc trả buffer về pool trước khi đã xử lý kết quả cuối cùng.
- Khi callback đã báo hoàn tất hoặc `Future.get()` thành công, chuẩn bị `flip`/`clear` mới an toàn theo luồng công việc thích hợp.

Ví dụ **sai**:

```java
ByteBuffer buf = ByteBuffer.allocate(1024);
Future<Integer> first = channel.read(buf, 0L);
buf.clear();                        // Sai: I/O first vẫn có thể pending.
Future<Integer> second = channel.read(buf, 1024L);
```

Hai thao tác cùng buffer có thể khiến vị trí/nội dung bị truy cập đồng thời ngoài hợp đồng an toàn. `ByteBuffer` không tự biến thành một vùng nhớ chia sẻ có đồng bộ chỉ vì API gọi bất đồng bộ.

Ví dụ **đúng về quyền sở hữu buffer**:

```java
ByteBuffer firstBuffer = ByteBuffer.allocate(1024);
ByteBuffer secondBuffer = ByteBuffer.allocate(1024);

Future<Integer> first = channel.read(firstBuffer, 0L);
Future<Integer> second = channel.read(secondBuffer, 1024L);

int n1 = first.get();
int n2 = second.get();
// Sau get thành công, mới xử lý hai buffer tương ứng.
```

Đây vẫn là đoạn minh họa. Trước khi giải mã, chỉ những byte tương ứng với kết quả hoàn tất là dữ liệu mới đọc hợp lệ. Nếu đọc partial, thiết kế parser phải xử lý phần còn thiếu. Không giả định `n1 == 1024` hoặc `n2 == 1024`.

**Lưu ý concurrency:** ngay cả khi hai buffer riêng, hai thao tác đọc cùng tệp trong khi thread khác ghi/truncate tệp vẫn có thể nhận dữ liệu không nhất quán. Buffer riêng giải quyết tranh chấp vùng nhớ của ứng dụng, không tạo snapshot nhất quán của tệp.

## 10. Tại sao không có current position chung?

Trong asynchronous I/O, thời điểm **được khởi tạo** và thời điểm **hoàn tất** của các request có thể khác nhau:

```text
T0: read(A, position=0)   ────────┐
T1: read(B, position=4096)    ──┐ │
T2: write(C, position=8192) ─┐ │ │
T3: write(C) completed       │ │ │
T4: read(B) completed          │ │
T5: read(A) completed            │
```

Nếu mọi request tự động chia sẻ một con trỏ và tăng khi completion xảy ra, vị trí thao tác sẽ khó xác định và phụ thuộc thứ tự hoàn tất. API dùng **offset tường minh ngay khi gửi request**, giúp mỗi thao tác xác định vùng dữ liệu của mình.

Tuy nhiên, **offset tường minh không chứng minh các I/O đồng thời tại cùng một vùng là nguyên tử hoặc có thứ tự xác định**. Khi hai write chồng lấn:

```text
write A: offset=100, length=10
write B: offset=105, length=10
              [cùng ghi byte 105..109]
```

Kết quả ở phần giao nhau có thể phụ thuộc lịch thực thi và provider; ứng dụng phải tránh ghi chồng lấn hoặc đồng bộ theo thứ tự logic. Với nhiều tác vụ cần đọc-sửa-ghi cùng record, một thao tác `read` rồi `write` không tạo transaction nguyên tử.

### Mô hình xử lý song song an toàn hơn

- Mỗi tác vụ có một **offset riêng được tính toán và kiểm tra**.
- Mỗi tác vụ sở hữu một **ByteBuffer riêng** trong suốt thời gian pending.
- Không ghi chồng lấn nếu không có cơ chế điều phối.
- Có giới hạn số lượng tác vụ concurrent để tránh quá tải thread pool, bộ nhớ, file descriptors hoặc I/O queue.
- Có chính sách timeout, retry, cancel và cleanup, nhất là khi lỗi xảy ra lúc nhiều Future khác vẫn pending.
- Nếu cần snapshot nhất quán, dùng thiết kế lưu trữ thích hợp (file bất biến theo version, khóa/chốt đồng bộ hoặc transaction ở tầng khác).

## 11. Completion, cancellation và lỗi

### Future exceptions

`Future.get()` có thể:

- Trả `Integer >= 0` khi thành công.
- Trả `-1` cho read ở EOF.
- Ném `InterruptedException` khi luồng đợi bị interrupt.
- Ném `ExecutionException` khi thao tác thất bại (kiểm tra `getCause()`).
- Ném `CancellationException` khi Future đã bị cancel theo hợp đồng Future.

Xử lý tổng quát:

```java
try {
    int n = pending.get();
    // Dựa vào n để quyết định parse, retry hoặc EOF.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Hủy/điều phối cleanup theo policy; không tái sử dụng buffer mù quáng.
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    // Log/truyền lỗi gốc phù hợp với tầng ứng dụng.
}
```

Đoạn này giả định `pending` có kiểu `Future<Integer>` và các exception được import. Nếu dữ liệu bắt buộc cập nhật đúng một lần, retry còn phải xét operation trước có thể đã ghi một phần.

### Đóng channel

`AsynchronousFileChannel` là `AutoCloseable`. Try-with-resources đóng channel khi thoát scope, nhưng ứng dụng nên **đảm bảo các request đã được chờ/hoàn tất trước khi scope kết thúc**. Nếu đóng channel khi còn thao tác pending, thao tác có thể thất bại với lỗi đóng channel như `AsynchronousCloseException` hoặc `ClosedChannelException` tùy thời điểm và cơ chế.

Không coi `close()` là một lệnh “chờ mọi callback xong, gửi toàn bộ kết quả và flush file” ở tầng nghiệp vụ. Thiết kế lifecycle rõ: dừng nhận request mới → đợi/điều phối các request đang chạy → xử lý callback/kết quả → thực hiện đồng bộ lưu trữ nếu cần → đóng channel/executor.

### FileLock

`AsynchronousFileChannel` có các thao tác khóa tệp bất đồng bộ và `tryLock`. File lock giúp phối hợp truy cập ở mức filesystem/provider nhưng không biến nhiều `read/write` thành transaction; tính bắt buộc/tư vấn của lock tùy nền tảng. Cũng cần đóng/release đúng vòng đời.

Nếu mục tiêu chỉ là truy cập các vùng file không chồng lấn, đừng thêm locking một cách tùy tiện: nó có thể tăng độ phức tạp và contention. Chỉ dùng khi có hợp đồng đồng thời cần bảo vệ rõ ràng.

## 12. `size()`, `truncate()`, `force()` và độ bền dữ liệu

Bên cạnh `read/write`, `AsynchronousFileChannel` còn có các phương thức hỗ trợ quản lý file:

| Phương thức | Ý nghĩa |
|---|---|
| `size()` | Trả kích thước file ở thời điểm gọi |
| `truncate(long size)` | Cắt đuôi file khi kích thước hiện tại lớn hơn tham số |
| `force(boolean metaData)` | Yêu cầu đồng bộ nội dung (và metadata nếu true) xuống thiết bị lưu trữ theo hợp đồng API |
| `lock(...)`, `tryLock(...)` | Hỗ trợ khóa file hoặc vùng file với semantics/provider tương ứng |
| `isOpen()`, `close()` | Quản lý trạng thái/vòng đời channel |

**`truncate` không tự mở rộng file** nếu size truyền vào lớn hơn độ dài hiện tại. Muốn mở rộng, phải dùng cơ chế ghi hoặc thiết kế dữ liệu phù hợp; không có `channel.position(newPosition)` để thay current position vì API này không có con trỏ chung đó.

`force(true)` giúp yêu cầu đồng bộ cập nhật đã thực hiện qua channel, nhưng không tự tạo transaction giữa nhiều lần write; durability cuối cùng phụ thuộc filesystem, thiết bị và provider. Muốn đảm bảo file hoàn chỉnh khi crash giữa nhiều thao tác write, cân nhắc ghi file tạm, kiểm tra, đồng bộ và thay thế đích phù hợp với semantics filesystem.

Khi đang có I/O pending, không nên `truncate` ngay mà kỳ vọng các lần read/write khác tự thực hiện theo thứ tự bạn hình dung. Điều phối các thao tác liên quan trước khi sửa kích thước file.

## 13. Hiệu năng và giới hạn tài nguyên

**Bất đồng bộ không tự động nhanh hơn đồng bộ.** Lợi ích chủ yếu xuất hiện khi ứng dụng có công việc khác để làm trong lúc chờ I/O, hoặc cần quản lý nhiều tác vụ độc lập mà không muốn mỗi request chiếm một luồng ứng dụng riêng đang chờ.

Khi đánh giá:

1. **Số lượng tác vụ pending:** quá nhiều Future/ByteBuffer có thể gây áp lực bộ nhớ và thread pool.
2. **Kích thước I/O:** đọc từng vài byte bất đồng bộ có thể có overhead lớn so với đọc/gửi theo block phù hợp.
3. **Executor/provider:** một số implementation dùng thread pool thực hiện file I/O; tối ưu bằng đo hiệu năng chứ không chỉ đổi API.
4. **Ổ đĩa và filesystem:** đặc tính NVMe/HDD/network filesystem, cache, flush và số I/O song song có thể thay đổi kết quả.
5. **Đồng thời và consistency:** chạy song song những write chồng lấn có thể làm dữ liệu sai dù throughput tăng.
6. **Độ trễ completion:** callback nhanh nên giao việc CPU nặng cho một executor khác hoặc luồng xử lý phù hợp; không chặn lâu thread của completion pool.
7. **Độ bền:** `force`, metadata update, sync và locking có thể thay đổi đáng kể latency; đừng bỏ chúng chỉ để benchmark đẹp nếu nghiệp vụ đòi hỏi.

Nếu nhu cầu chỉ đọc một file nhỏ một lần rồi đợi ngay, `Files.readAllBytes` hay `FileChannel` đồng bộ có thể đơn giản hơn và đủ tốt. Chọn `AsynchronousFileChannel` khi **mô hình completion/parallel requests** thực sự giúp kiến trúc.

## 14. Các lỗi thường gặp

1. **Tưởng có current position của AsynchronousFileChannel.** Không có; mọi `read/write` nhận `long position`.
2. **Không tăng offset sau partial I/O.** Lần gọi tiếp có thể đọc lặp/ghi đè byte cũ.
3. **Tin rằng một lần read/write xử lý hết buffer.** Kiểm tra kết quả, remaining và EOF.
4. **Gọi `future.get()` ngay rồi vẫn quảng cáo ứng dụng hoàn toàn không block.** `get` có thể chờ; async API không làm luồng chờ tự biến mất.
5. **Nhầm `Future.get()` với `ByteBuffer.get()`.** Cái đầu trả số byte I/O sau completion; cái sau đọc byte từ buffer theo position.
6. **Tái dùng ByteBuffer trước completion.** Có thể gây lỗi dữ liệu hoặc vi phạm hợp đồng truy cập buffer trong lúc pending.
7. **Dùng cùng buffer cho nhiều request cùng lúc.** Dù offset tệp khác nhau, position/nội dung buffer vẫn tranh chấp.
8. **Nhầm EOF `-1` với read `0`.** `0` có thể nghĩa là chưa đọc byte nào; `-1` là hết dữ liệu ở vị trí đó.
9. **Quên `flip()` trước khi decode buffer đã được đọc vào.** Decoder có thể thấy remaining sai hoặc không thấy dữ liệu mới.
10. **Không quản lý `InterruptedException` đúng.** Khôi phục interrupt flag khi không tiêu thụ interrupt có chủ đích và thực hiện cleanup phù hợp.
11. **Cho rằng callback chạy trên cùng thread hoặc theo thứ tự submit.** Thứ tự completion không phải thứ tự khởi tạo.
12. **Đóng channel/executor khi còn I/O pending.** Thao tác có thể thất bại; cần chính sách shutdown/lifecycle rõ.
13. **Dùng `Selector` với AsynchronousFileChannel.** API này không phải selectable channel.
14. **Gửi APPEND khi mở channel.** `AsynchronousFileChannel` không hỗ trợ kiểu append mở tệp như vậy.
15. **Dùng `size()` rồi ghi tại size như append atomic giữa nhiều writer.** Hai writer có thể chọn cùng offset; cần điều phối.
16. **Coi offset độc lập là dữ liệu độc lập.** Các write cùng vùng vẫn có race; truncate có thể ảnh hưởng request khác.
17. **Cho rằng cancel Future luôn đảo ngược phần write đã thực hiện.** Không có transaction/rollback; retry cần thiết kế idempotency.
18. **Chỉ tối ưu số thread mà bỏ qua storage đặc thù.** Benchmark trên loại thiết bị, quy mô và pattern I/O thực tế.

## 15. Khi nào nên chọn AsynchronousFileChannel?

### Trường hợp A — Xử lý nhiều record theo offset độc lập

Tệp record fixed-size, có một số đoạn đã biết vị trí. Bạn có thể submit các `read(buffer, offset)` song song với **buffer riêng cho mỗi request**, rồi xử lý kết quả khi tất cả hoàn tất. Mẫu này có ích nếu tầng ứng dụng muốn concurrency và không cần con trỏ chung.

### Trường hợp B — Server cần chồng lấp công việc với file I/O

Một request cần nạp một đoạn file lớn, nhưng thread xử lý còn công việc khác. Có thể submit file read và tiếp tục xử lý các phần độc lập, sau đó callback/Future báo sẵn sàng. Lưu ý backpressure và số buffer đang tồn tại.

### Trường hợp C — Chỉnh sửa file tuần tự ít lần

Nếu chương trình đọc 100 byte, xử lý rồi ghi 20 byte và luôn chờ ngay, `FileChannel` hoặc `RandomAccessFile` có thể đơn giản hơn. `AsynchronousFileChannel` không bắt buộc chỉ vì tệp lớn.

### Trường hợp D — Nhiều writer vào cùng cuối tệp

Không chỉ gọi `channel.write(buffer, channel.size())` đồng thời và kỳ vọng append đúng thứ tự. `size()` là một snapshot tại thời điểm gọi; hai writer có thể chọn cùng offset. Cần một allocator offset đồng bộ, một writer tuần tự, record log có kiến trúc riêng hoặc cơ chế lưu trữ có append/transaction phù hợp.

### Trường hợp E — Muốn stream mạng event-driven

Nếu tác vụ là network TCP/UDP chứ không phải file I/O, hãy chọn API network tương ứng như `SocketChannel` + `Selector` hoặc nhóm `AsynchronousSocketChannel`, không cố dùng `AsynchronousFileChannel` cho socket.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `AsynchronousFileChannel` có `channel.position(100L)` như `FileChannel` không?  
**Không.** Mỗi `read/write` có `long position` tường minh.

**Câu 2.** Gọi `read(buffer, 100L)` nhận `Future<Integer>`, sau khi `get()` trả 40. Muốn đọc phần tiếp theo ở offset nào?  
**Offset 140**, với điều kiện buffer còn remaining và format yêu cầu đọc tiếp.

**Câu 3.** Gọi `write(source, 500L)`, `get()` trả 10 nhưng source vẫn còn 8 byte. Lời ghi tiếp nên bắt đầu ở đâu?  
**Offset 510.** Chờ lần ghi trước hoàn tất rồi `write(source, 510L)`.

**Câu 4.** Có thể gọi `buffer.clear()` khi Future read còn pending không?  
**Không nên;** buffer thuộc thao tác đang chạy. Chờ completion/thiết kế quyền sở hữu trước khi đổi trạng thái buffer.

**Câu 5.** Nếu dùng `Future.get()` ngay sau khi submit thì code có nhất thiết không block không?  
**Không.** `get()` có thể chặn luồng gọi cho tới completion.

**Câu 6.** Hai read ở offset 0 và 4096 với hai buffer riêng có phải luôn trả về theo thứ tự submit không?  
**Không.** Thứ tự completion có thể khác. Nếu cần xử lý theo thứ tự, ứng dụng phải điều phối kết quả.

**Câu 7.** `AsynchronousFileChannel` có thể đăng ký `Selector.OP_READ` không?  
**Không.** Nó không phải `SelectableChannel`.

**Câu 8.** `channel.size()` là 1000; hai writer cùng submit `write(buffer,1000L)`. Có được bảo đảm nối tiếp mà không chồng byte không?  
**Không.** Các thao tác dùng cùng offset và có thể ghi chồng lấn. Cần cấp phát offset/serialization trước khi submit.

**Câu 9.** Một write trả thành công nghĩa là dữ liệu đã bền vững qua mất điện chưa?  
**Chưa chắc.** Cần chính sách durability, ví dụ `force` khi phù hợp, và hiểu giới hạn provider/filesystem.

## 17. Tổng kết

- `AsynchronousFileChannel` là API file I/O bất đồng bộ với **offset tường minh cho từng lần đọc/ghi**; nó không có current file position kiểu `FileChannel`.
- `read/write(ByteBuffer, long)` trả `Future<Integer>`; overload có attachment và `CompletionHandler` cho phép nhận completion qua callback.
- **Số byte thành công có thể nhỏ hơn remaining**; cần tăng offset bằng lượng byte thực tế và xử lý EOF.
- **ByteBuffer phải được giữ ổn định khi thao tác còn pending**; không tái sử dụng một buffer cho các request chồng nhau.
- **Offset riêng giúp tổ chức concurrency**, nhưng không tự làm dữ liệu đồng thời nhất quán và không thay thế lock/transaction.
- Bất đồng bộ là một **mô hình lập trình**, không phải cam kết tốc độ cao hơn trong mọi điều kiện; hãy đo hiệu năng và quản lý tài nguyên có giới hạn.

### Tài liệu API Java SE 17

- [AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html)
- [CompletionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html)
- [FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html)
- [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
