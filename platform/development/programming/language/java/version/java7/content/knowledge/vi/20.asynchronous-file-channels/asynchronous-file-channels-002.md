# Vai trò của AsynchronousFileChannel trong Java: đọc và ghi tệp bất đồng bộ

**Chủ đề:** Java 7 — Kênh tệp bất đồng bộ  
**Bài học:** Vai trò của `AsynchronousFileChannel`  
**Môi trường thực hành:** Java 17+; các API NIO.2 trong `java.nio.channels` và `java.nio.file`. `AsynchronousFileChannel` được giới thiệu từ Java 7, **vẫn là API hiện hành**, và tất cả chương trình mẫu ở đây dùng những khả năng còn áp dụng trong Java hiện đại.

## 1. Tại sao Java cần AsynchronousFileChannel?

Một tác vụ đọc/ghi tệp có thể mất thời gian: filesystem cần tìm dữ liệu, đưa dữ liệu từ thiết bị hoặc cache vào RAM, ghi khối dữ liệu mới, xử lý quyền truy cập và cập nhật metadata. Trong cách viết **đồng bộ**, thread gọi thường đợi đến khi thao tác chuyển dữ liệu kết thúc:

```java
try (FileChannel channel =
        FileChannel.open(path, StandardOpenOption.READ)) {
    ByteBuffer buffer = ByteBuffer.allocate(4096);
    int n = channel.read(buffer);
    // Khi read trả về, số byte đọc đã được biết.
}
```

Đây là **snippet minh họa**, chưa có khai báo `path` và import. `FileChannel` có nhiều ưu điểm: API đơn giản, có vị trí hiện tại, hỗ trợ `transferTo/transferFrom`, mapping và các thao tác đồng bộ hữu ích.

Với `AsynchronousFileChannel`, ứng dụng **khởi tạo thao tác đọc/ghi**, nhận một đối tượng đại diện kết quả tương lai hoặc đăng ký callback, rồi có thể thực hiện công việc khác trước khi I/O hoàn tất:

```java
Future<Integer> pending = channel.read(buffer, 0L);
// Có thể làm công việc khác; không cần đợi ngay tại lệnh read.
int transferred = pending.get();
```

Đây là **snippet**, cần channel, buffer, imports và xử lý exceptions. `pending.get()` vẫn **chặn thread hiện tại** cho đến khi kết quả sẵn sàng nếu chưa hoàn tất. Vì vậy lợi ích bất đồng bộ xuất hiện rõ nhất khi thiết kế không gọi `get()` ngay hoặc có nhiều công việc/I/O chồng lấp.

**Vai trò chính của `AsynchronousFileChannel`**: cung cấp một API **I/O tệp dựa trên hoàn tất thao tác (completion-based)**, với từng lần đọc/ghi mang **file offset riêng**, kết quả bất đồng bộ dưới dạng `Future<Integer>` hoặc `CompletionHandler<Integer,A>`, và khả năng có nhiều I/O đang chờ đồng thời. Nó giúp tách lịch thực thi công việc khỏi thời gian hoàn tất I/O, **không phải lời hứa mọi hoạt động đĩa sẽ nhanh hơn**.

### 1.1. Ba điều thường bị nhầm

1. **Asynchronous ≠ chạy nhanh hơn về mặt phần cứng.** I/O vẫn có latency và throughput hữu hạn; scheduling, executor và overhead còn có thể khiến tác vụ nhỏ chậm hơn API đơn giản.
2. **Asynchronous ≠ mọi thread đều không bao giờ bị block.** Implementation có thể dùng thread pool để chờ hoặc xử lý I/O. JavaDoc mô tả channel gắn với thread pool; cách OS thực hiện bên dưới là implementation-dependent.
3. **Asynchronous ≠ tự động đảm bảo thứ tự/atomicity.** Hai thao tác đang chờ có thể hoàn tất theo thứ tự khác với khi khởi tạo. Nếu ghi vào các vùng chồng lấp, ứng dụng phải tự định nghĩa chính sách phối hợp.

### 1.2. Hình dung một chuỗi công việc

```text
Thread của ứng dụng        AsynchronousFileChannel         File storage
        |                             |                           |
        |  read(buffer, offset)       |                           |
        |---------------------------->|---- yêu cầu đọc ---------->|
        |  Future / return ngay       |                           |
        |<----------------------------|                           |
        |  xử lý request khác         |                           |
        |                             |<--- hoàn tất I/O ----------|
        |  Future sẵn sàng /          |                           |
        |  CompletionHandler chạy     |                           |
        |<----------------------------|                           |
        |  xử lý bytes hợp lệ         |                           |
```

Đây là sơ đồ khái niệm, **không cam kết** channel phải dùng native kernel async I/O hay callback chạy trên một thread bất kỳ. Theo JavaDoc, completion handlers được dispatch bằng **thread pool gắn với channel**; một callback đôi khi có thể chạy trực tiếp khi lời gọi xuất phát từ chính thread của pool và thao tác hoàn tất ngay.

## 2. Các thành phần của API và ý nghĩa

`AsynchronousFileChannel` là class abstract triển khai `AsynchronousChannel`, `Channel` và `AutoCloseable`. Những API trọng tâm:

| API | Vai trò | Đồng bộ hay bất đồng bộ? |
| --- | --- | --- |
| `AsynchronousFileChannel.open(path, options...)` | Mở hoặc tạo channel, chọn READ/WRITE và options | Mở channel là lời gọi trực tiếp, không trả Future |
| `read(ByteBuffer dst, long position)` | Khởi động đọc từ offset; trả `Future<Integer>` | Bất đồng bộ về kết quả |
| `read(dst, position, attachment, handler)` | Khởi động đọc và gọi handler khi xong/lỗi | Bất đồng bộ về kết quả |
| `write(ByteBuffer src, long position)` | Khởi động ghi từ offset; trả `Future<Integer>` | Bất đồng bộ về kết quả |
| `write(src, position, attachment, handler)` | Khởi động ghi và gọi handler khi xong/lỗi | Bất đồng bộ về kết quả |
| `lock()` / `lock(position,size,shared)` | Yêu cầu lấy khóa vùng file; trả `Future<FileLock>` | Bất đồng bộ |
| `lock(..., handler)` | Lấy khóa và thông báo qua callback | Bất đồng bộ |
| `tryLock(...)` | Thử lấy khóa ngay, có thể trả `null` | Không đợi khóa khác nhả |
| `size()` | Lấy độ dài file hiện tại | Lời gọi trực tiếp, có thể làm I/O |
| `truncate(size)` | Rút ngắn file nếu cần | Lời gọi trực tiếp |
| `force(metaData)` | Yêu cầu đẩy cập nhật tới storage theo contract | Lời gọi trực tiếp; có thể tốn thời gian |
| `isOpen()` / `close()` | Xem/trả quyền sở hữu vòng đời channel | Lời gọi trực tiếp, đóng có thể ảnh hưởng I/O đang chờ |

**Điểm đặc biệt:** `AsynchronousFileChannel` **không có một “current file position” dùng chung**. Mỗi read/write nhận `long position` riêng. Đây là sự khác biệt cơ bản với dạng đọc/ghi tuần tự của `FileChannel`.

### 2.1. offset là vị trí byte, không phải ký tự

`position = 0L` bắt đầu ở byte đầu tiên. `position = 5L` bắt đầu tại byte offset 5. Trong UTF-8, một ký tự Unicode có thể chiếm nhiều byte; không được dùng chỉ số ký tự String làm offset để ghi tệp có encoding biến độ dài.

Trong code thực hành, khi cần ghi văn bản thành byte array, dùng `text.getBytes(StandardCharsets.UTF_8)`. Khi đọc, đưa bytes đã nhận vào decoder phù hợp, tránh giả định một chunk luôn kết thúc đúng ranh giới ký tự UTF-8.

**Không truyền offset âm:** API có thể ném `IllegalArgumentException` ngay tại lúc khởi tạo lời gọi, trước khi có `Future`. Nếu đọc tới/qua EOF, kết quả `Future.get()` hoặc callback có thể là **`-1`**, không phải luôn 0.

## 3. Cách mở channel và vòng đời tài nguyên

Lựa chọn đơn giản nhất:

```java
try (AsynchronousFileChannel ch =
        AsynchronousFileChannel.open(
            path, StandardOpenOption.READ)) {
    // Thực hiện các I/O, đợi/ghi nhận kết quả trước khi rời scope.
}
```

Đây là **snippet**. Những options thường gặp:

| StandardOpenOption | Ý nghĩa |
| --- | --- |
| `READ` | Mở cho thao tác đọc |
| `WRITE` | Mở cho thao tác ghi |
| `CREATE_NEW` | Tạo file mới; nếu entry đã tồn tại thì thất bại |
| `CREATE` | Tạo khi chưa tồn tại; nếu đã tồn tại thì mở |
| `TRUNCATE_EXISTING` | Rút ngắn file đang tồn tại khi mở để ghi |
| `DELETE_ON_CLOSE` | Yêu cầu xóa khi đóng theo best effort |
| `SYNC` / `DSYNC` | Thay đổi chính sách đồng bộ cập nhật theo khả năng provider |

**Không dùng `APPEND` như lựa chọn mặc định cho `AsynchronousFileChannel`**: API tập trung vào **positional write**, không có shared cursor để append theo thứ tự. Các standard options được tài liệu class liệt kê không bao gồm `APPEND` trong nhóm được bảo đảm; nếu cần append an toàn giữa nhiều writers, phải thiết kế cấp phát offset/transaction hoặc dùng một abstraction phù hợp.

File path thuộc filesystem provider cụ thể. Không giả định `AsynchronousFileChannel.open` hỗ trợ mọi provider (chẳng hạn ZIPFS hoặc filesystem ảo); `UnsupportedOperationException` có thể xuất hiện. Trong các chương trình mẫu, ta dùng filesystem mặc định của hệ điều hành.

**Quản lý tài nguyên:**

- Đóng channel bằng `try-with-resources`.
- **Không đóng** channel ngay sau khi khởi tạo I/O nếu còn muốn đợi nó thành công.
- Trong thử nghiệm dùng `Future.get(timeout)` hoặc `CountDownLatch.await(timeout)` để xác nhận I/O hoàn tất trước khi scope kết thúc.
- Nếu có executor riêng, đóng channel trước, sau đó shutdown executor có kiểm soát.
- Không sử dụng `isOpen()` như bảo đảm I/O tiếp theo thành công: thread khác có thể close ngay sau lần kiểm tra.
- Với lỗi trong callback, gửi lỗi đến state/future/log phù hợp; không chỉ ném exception trên callback thread rồi để caller hiểu nhầm mọi thứ đã thành công.

## 4. Future<Integer>: bắt đầu đọc và nhận kết quả sau

Một lần đọc theo Future:

```java
Future<Integer> pending = channel.read(buffer, offset);
int n = pending.get(5, TimeUnit.SECONDS);
```

Đây là snippet. `read` có thể trả Future **trước khi bytes sẵn sàng**; `get` chờ tối đa thời hạn yêu cầu. Các kết quả đáng quan tâm:

- `n > 0`: đúng `n` bytes đã được chuyển vào buffer; tăng offset thêm `n`.
- `n == 0`: không có byte được chuyển trong lần đó; không nên coi đã hoàn tất file.
- `n == -1`: EOF tại offset được dùng vào thời điểm đọc.
- `get` ném `TimeoutException`: việc chờ kết quả hết hạn; **không tự khẳng định I/O bên dưới đã bị hủy**.
- `get` ném `ExecutionException`: thao tác hoàn tất bằng lỗi, kiểm tra `getCause()`.
- `get` ném `InterruptedException`: thread chờ bị interrupt; cần giữ chính sách interrupt của ứng dụng.

### 4.1. Ví dụ runnable: đọc bằng Future với offset cụ thể

Lưu thành `AsyncFutureReadDemo.java`:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.file.*;
import java.util.concurrent.*;
public class AsyncFutureReadDemo {
  public static void main(String[] args) throws Exception {
    Path path=Files.createTempFile("async-read-", ".txt");
    try {
      Files.writeString(path,"HELLO-ASYNC",StandardCharsets.UTF_8);
      try(AsynchronousFileChannel channel=AsynchronousFileChannel.open(path,StandardOpenOption.READ)){
        ByteBuffer bytes=ByteBuffer.allocate(11);
        int total=0;
        while(bytes.hasRemaining()){
          Future<Integer> result=channel.read(bytes,total);
          int n=result.get(5,TimeUnit.SECONDS);
          if(n<0) throw new IOException("Unexpected EOF");
          total+=n;
        }
        bytes.flip();
        System.out.println("bytes="+total);
        System.out.println("text="+StandardCharsets.UTF_8.decode(bytes));
      }
    }finally{Files.deleteIfExists(path);}
  }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac -encoding UTF-8 -Xlint:all AsyncFutureReadDemo.java
java AsyncFutureReadDemo
```

**stdout đã kiểm thử:**

```text
bytes=11
text=HELLO-ASYNC
```

Chương trình dùng file tạm với chuỗi **11 byte ASCII**, nên việc tính byte count xác định trên mọi hệ điều hành. Vòng `while(bytes.hasRemaining())` tránh giả định một lần `read` luôn điền đầy buffer.

**Điều nên lưu ý:**

- `ByteBuffer.allocate(11)` tạo buffer với `position=0`, `limit=11`.
- `channel.read(bytes,total)` khởi tạo đọc từ vị trí tệp `total`.
- `get(5,SECONDS)` chỉ được dùng để chứng minh kết quả và đưa demo tới trạng thái xác định; một ứng dụng không muốn block thread nên dùng callback hoặc kết hợp công việc khác.
- `bytes.flip()` chuyển buffer từ trạng thái **ghi bytes vào buffer** sang trạng thái **đọc bytes khỏi buffer**.
- `StandardCharsets.UTF_8.decode(bytes)` ở demo dùng dữ liệu ASCII/UTF-8 hoàn chỉnh; với chunks chứa Unicode nhiều byte, cần decoder có trạng thái nếu các ký tự bị chia ở ranh giới chunk.
- File tạm được xóa trong `finally` sau khi channel đóng.

Nếu muốn đọc một file có độ dài bất kỳ, không thể cố cấp buffer đúng bằng một `length` lấy từ metadata rồi tin file không đổi. Nên stream/chunk và xử lý EOF, giới hạn dung lượng, thay đổi đồng thời và kết quả từng phần.

## 5. Future<Integer> khi ghi: phải tăng offset theo số byte đã ghi

`write(ByteBuffer, position)` trả một `Future<Integer>`. Số bytes được chuyển trong **lần ghi đó** có thể nhỏ hơn phần còn lại của buffer. Lỗi thường gặp:

```java
channel.write(buffer, 0L);
channel.close(); // Sai: chưa đợi Future, kết quả có thể không được ghi.
```

Đây là snippet minh họa cách làm **không an toàn**. Một lỗi khác là gọi nhiều lần `channel.write(buffer, 0L)` mà không tăng offset: các bytes có thể được ghi chồng vào cùng vùng file.

Mẫu đúng về nguyên tắc:

```java
long position = 0L;
while (buffer.hasRemaining()) {
    int n = channel.write(buffer, position).get();
    if (n <= 0) {
        throw new IOException("Write made no progress");
    }
    position += n;
}
```

Đây là snippet trong một method cho phép các checked exceptions. Trong sản phẩm thật, xử lý timeout, interruption, file growth, quota và deadline; đừng để `get()` chờ vô hạn.

### 5.1. Ví dụ runnable: tạo tệp và ghi hết buffer

Lưu thành `AsyncFutureWriteDemo.java`:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.file.*;
import java.util.concurrent.TimeUnit;
public class AsyncFutureWriteDemo {
  public static void main(String[] args)throws Exception{
    Path dir=Files.createTempDirectory("async-write-");
    Path path=dir.resolve("result.txt");
    try{
      long position=0;
      try(AsynchronousFileChannel channel=AsynchronousFileChannel.open(
              path,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)){
        ByteBuffer source=ByteBuffer.wrap("HELLO".getBytes(StandardCharsets.UTF_8));
        while(source.hasRemaining()){
          int n=channel.write(source,position).get(5,TimeUnit.SECONDS);
          if(n<=0)throw new IOException("No write progress");
          position+=n;
        }
        channel.force(false);
      }
      System.out.println("written="+position);
      System.out.println("readback="+Files.readString(path,StandardCharsets.UTF_8));
    }finally{
      Files.deleteIfExists(path);
      Files.deleteIfExists(dir);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AsyncFutureWriteDemo.java
java AsyncFutureWriteDemo
```

**stdout đã kiểm thử:**

```text
written=5
readback=HELLO
```

Giải thích:

1. `CREATE_NEW` dùng tên file mới trong thư mục tạm; nếu file đã tồn tại, operation thất bại thay vì ghi đè ngoài ý muốn.
2. Buffer chứa năm bytes UTF-8 ASCII.
3. Mỗi lần `write` ghi từ **position hiện tại**, và position tăng theo **số bytes thực sự hoàn tất**.
4. `force(false)` được gọi **sau** khi mọi Future ghi đã hoàn thành. `force` là lời gọi trực tiếp và có thể block; tham số `false` ưu tiên bảo đảm cập nhật nội dung hơn là mọi metadata, theo hợp đồng đối với local device.
5. Channel đóng trước khi đọc lại bằng `Files.readString`.
6. Dữ liệu được kiểm tra và dọn an toàn.

**Đừng suy `force(false)` đảm bảo dữ liệu bất biến vĩnh viễn:** trên network storage, JavaDoc không đưa cùng bảo đảm như local storage; power loss, controller caches, replication và filesystem semantics còn ảnh hưởng. `force` cũng không tự biến nhiều files thành một transaction.

## 6. CompletionHandler: xử lý kết quả mà không gọi get()

`AsynchronousFileChannel` có overload:

```java
<A> void read(
        ByteBuffer dst, long position,
        A attachment, CompletionHandler<Integer, ? super A> handler);

<A> void write(
        ByteBuffer src, long position,
        A attachment, CompletionHandler<Integer, ? super A> handler);
```

Đây là chữ ký minh họa của hai overload; `A` là kiểu **attachment** mà bạn gửi đi cùng yêu cầu và nhận lại trong `completed` hoặc `failed`.

Interface `CompletionHandler<V,A>` có:

- `completed(V result, A attachment)`: được gọi khi I/O hoàn tất thành công.
- `failed(Throwable exc, A attachment)`: được gọi nếu operation thất bại.

Một callback nên **nhanh**: cập nhật trạng thái, hoàn tất promise/future hoặc enqueue công việc nặng sang executor phù hợp. Nếu parse file lớn hoặc chờ database ngay trong callback, bạn có thể chiếm threads được dùng để dispatch I/O completions.

### 6.1. Ví dụ runnable: callback đọc và báo hoàn tất

Lưu thành `AsyncCompletionHandlerDemo.java`:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.*;
import java.nio.file.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
public class AsyncCompletionHandlerDemo {
  public static void main(String[] args)throws Exception{
    Path path=Files.createTempFile("async-handler-", ".txt");
    try{
      Files.writeString(path,"CALLBACK",StandardCharsets.UTF_8);
      try(AsynchronousFileChannel channel=AsynchronousFileChannel.open(path,StandardOpenOption.READ)){
        ByteBuffer buffer=ByteBuffer.allocate(8);
        CountDownLatch done=new CountDownLatch(1);
        AtomicReference<Throwable> error=new AtomicReference<>();
        CompletionHandler<Integer,Long> handler=new CompletionHandler<>(){
          public void completed(Integer n,Long offset){
            if(n<0){error.set(new IOException("Unexpected EOF"));done.countDown();return;}
            long next=offset+n;
            if(buffer.hasRemaining())channel.read(buffer,next,next,this);
            else done.countDown();
          }
          public void failed(Throwable failure,Long offset){
            error.set(failure);
            done.countDown();
          }
        };
        channel.read(buffer,0L,0L,handler);
        if(!done.await(5,TimeUnit.SECONDS))throw new IOException("Timeout");
        if(error.get()!=null)throw new IOException("Read failure",error.get());
        int count=buffer.position();
        buffer.flip();
        System.out.println("bytes="+count);
        System.out.println("text="+StandardCharsets.UTF_8.decode(buffer));
      }
    }finally{Files.deleteIfExists(path);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AsyncCompletionHandlerDemo.java
java AsyncCompletionHandlerDemo
```

**stdout đã kiểm thử:**

```text
bytes=8
text=CALLBACK
```

**Vai trò từng phần:**

- `handler` nhận `Integer n` là số bytes của **lần đọc vừa hoàn tất**.
- `Long offset` là **attachment** mô tả vị trí bắt đầu lần đọc; callback tính `next=offset+n` để tiếp tục nếu buffer vẫn còn chỗ.
- `AtomicReference<Throwable>` giữ lỗi xuyên thread một cách an toàn.
- `CountDownLatch` đồng bộ thread main với callback, để buffer chỉ được đọc **sau khi tất cả I/O của demo hoàn thành**.
- `channel.read(..., this)` từ callback tạo lần đọc tiếp theo. Không chia sẻ buffer ấy với một read/write đang chạy song song.
- `CountDownLatch.await(5,SECONDS)` trong chương trình thử nghiệm chỉ để có stdout xác định. Đây không phải một loop event-driven production hoàn chỉnh.

**Chú ý với `n==0`:** chương trình demo tiếp tục yêu cầu đọc và phù hợp file tạm tại chỗ; với filesystem có điều kiện đặc biệt, nên thiết kế giới hạn retry/deadline để tránh lặp quá mức. Với data file mới có thể bị thay đổi bởi writer khác, cần policy phát hiện EOF, partial changes và sự kiện file replacement.

### 6.2. Attachment khác kết quả I/O

`attachment` **không** phải số byte đọc hay dữ liệu do OS tạo. Đây là dữ liệu ứng dụng gắn vào mỗi operation, ví dụ:

- ID của request cần callback.
- Vị trí file/offset đang thực hiện.
- Đối tượng trạng thái của một thao tác nhiều chunk.
- Correlation ID/trace context.
- Tham chiếu tới queue hoặc promise được quản lý theo vòng đời.

Nếu đặt một object mutable làm attachment và chia sẻ nó với nhiều callback, phải có synchronization thích hợp. Chỉ riêng `CompletionHandler` không tự biến object mutable thành thread-safe.

## 7. Không có current position: nhiều reads ở các offset độc lập

Khác với cách đọc tuần tự trên một `FileChannel` có thể dựa vào shared cursor, `AsynchronousFileChannel` **yêu cầu offset riêng cho từng read/write**. Điều này phù hợp với xử lý nhiều đoạn file độc lập, ví dụ một block từ đầu file và một block khác ở giữa.

**Tác dụng thực tế:**

- Scheduler có thể phát nhiều read requests cho những phạm vi khác nhau.
- Buffer và offset được gắn với từng request; không phải tranh chấp một current position.
- Dễ định nghĩa công việc chia đoạn nếu biết file size/version.
- **Không được** giả định hai requests sẽ hoàn tất theo thứ tự gửi hoặc tốc độ cao hơn single sequential read.

**Giới hạn:** nhiều ghi chồng lấp tại cùng phạm vi có thể làm dữ liệu cuối khó xác định. Tránh overlap hoặc điều phối bằng transaction, partition/ownership hay synchronization rõ ràng.

### 7.1. Ví dụ runnable: hai thao tác đọc đang chờ ở hai offset

Lưu thành `AsyncPositionalReadsDemo.java`:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.file.*;
import java.util.concurrent.*;
public class AsyncPositionalReadsDemo {
  static void complete(AsynchronousFileChannel channel,ByteBuffer buffer,
                       long start,Future<Integer> first)throws Exception {
    long position=start;
    int n=first.get(5,TimeUnit.SECONDS);
    if(n<0)throw new IOException("Unexpected EOF");
    position+=n;
    while(buffer.hasRemaining()){
      n=channel.read(buffer,position).get(5,TimeUnit.SECONDS);
      if(n<0)throw new IOException("Unexpected EOF");
      position+=n;
    }
  }
  public static void main(String[] args)throws Exception {
    Path file=Files.createTempFile("async-offset-", ".txt");
    try{
      Files.writeString(file,"ABCDEFGHIJ",StandardCharsets.UTF_8);
      try(AsynchronousFileChannel channel=AsynchronousFileChannel.open(file,StandardOpenOption.READ)){
        ByteBuffer first=ByteBuffer.allocate(5);
        ByteBuffer second=ByteBuffer.allocate(5);
        Future<Integer> pendingFirst=channel.read(first,0L);
        Future<Integer> pendingSecond=channel.read(second,5L);
        complete(channel,first,0L,pendingFirst);
        complete(channel,second,5L,pendingSecond);
        first.flip();second.flip();
        System.out.println("first="+StandardCharsets.UTF_8.decode(first));
        System.out.println("second="+StandardCharsets.UTF_8.decode(second));
        System.out.println("both-positions-independent=true");
      }
    }finally{Files.deleteIfExists(file);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AsyncPositionalReadsDemo.java
java AsyncPositionalReadsDemo
```

**stdout đã kiểm thử:**

```text
first=ABCDE
second=FGHIJ
both-positions-independent=true
```

Hai lần `channel.read` đầu tiên được khởi tạo liên tiếp, **trước khi** chương trình gọi `get` cho lần thứ nhất. Điều đó tạo hai thao tác có khả năng đang chờ chồng lấp. Mỗi thao tác sử dụng **buffer riêng** và offset `0` hoặc `5`.

Hàm `complete` nhận Future đầu tiên rồi **đọc nốt phần còn thiếu** nếu một lần read không điền đầy buffer. Vì file demo chứa mười bytes cố định, hai nửa đều đọc được hoàn chỉnh.

Không suy từ việc stdout in `ABCDE` trước `FGHIJ` rằng I/O ở offset 0 luôn hoàn tất trước offset 5. **Thứ tự in do main thread chọn**, không phải thứ tự hoàn tất được API cam kết.

## 8. ByteBuffer và các rủi ro khi I/O đang chờ

`ByteBuffer` là nơi giao tiếp giữa I/O channel và dữ liệu trong bộ nhớ. Nó có:

- **`capacity`:** tổng số bytes có thể chứa.
- **`position`:** vị trí đọc/ghi tiếp theo trong buffer.
- **`limit`:** giới hạn hiện tại đối với các thao tác buffer.
- **`remaining()`:** số bytes giữa position và limit.

Đối với **read** vào buffer:

1. Tạo buffer có dung lượng phù hợp.
2. Gọi `channel.read(buffer, fileOffset)`.
3. **Chờ completion** qua Future hoặc callback trước khi đọc/sửa buffer.
4. Nếu `n > 0`, buffer position phản ánh bytes nhận được.
5. `flip()` buffer để consumer đọc bytes.
6. `clear()`/`compact()` theo chiến lược xử lý chunks tiếp theo.

Đối với **write** từ buffer:

1. Đưa dữ liệu vào buffer và `flip()` nếu trước đó dùng `put(...)`.
2. Gọi `channel.write(buffer, fileOffset)`.
3. Trong khi I/O đang chờ, **không thay đổi** buffer hoặc dùng chung buffer vào operation khác.
4. Khi hoàn tất, tăng file offset đúng **`n` bytes thực tế**; nếu `buffer.hasRemaining()`, lên lịch lần ghi tiếp.
5. Chỉ tái sử dụng buffer sau completion và sau khi dữ liệu cần thiết đã được tiêu thụ.

**Cảnh báo:** `ByteBuffer` không tự thread-safe. Việc channel cho phép nhiều I/O đang chờ **không có nghĩa bạn được phép đồng thời dùng cùng một `ByteBuffer`** cho nhiều requests. JavaDoc nêu rõ không nên truy cập buffer cho đến khi operation hoàn tất; kết quả có thể không xác định khi thay đổi buffer trong thời gian I/O còn pending.

### 8.1. Lựa chọn heap và direct buffers

`ByteBuffer.allocate(size)` tạo heap buffer. `ByteBuffer.allocateDirect(size)` tạo direct buffer mà một số I/O implementation có thể sử dụng hiệu quả hơn. **Không có cam kết** direct buffer luôn nhanh hơn; allocation, GC pressure, memory ownership, buffer reuse và OS/provider đều ảnh hưởng.

Trong chương trình nhỏ, dùng heap buffer để đơn giản. Với pipeline throughput cao, đo benchmark thực tế với buffer sizes, concurrency và file sizes tương ứng, không tự suy direct buffer là bắt buộc.

### 8.2. Nhiều chunk và EOF

Không giả định một lần `read` điền đầy buffer. Với file lớn, dùng các lần đọc có offset tăng dần cho đến khi gặp EOF. Với charset nhiều byte, phải xử lý ranh giới decode; nếu nội dung là binary, giữ nguyên bytes.

### 8.3. Ví dụ runnable: đọc file theo nhiều chunk

Lưu thành `AsyncChunkedReadDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.file.*;
import java.util.Arrays;
import java.util.concurrent.TimeUnit;
public class AsyncChunkedReadDemo {
  public static void main(String[] args)throws Exception{
    Path file=Files.createTempFile("async-chunks-", ".bin");
    byte[] original="0123456789".repeat(250).getBytes(StandardCharsets.UTF_8);
    try{
      Files.write(file,original);
      ByteArrayOutputStream result=new ByteArrayOutputStream();
      int requests=0;
      try(AsynchronousFileChannel channel=AsynchronousFileChannel.open(file,StandardOpenOption.READ)){
        ByteBuffer buffer=ByteBuffer.allocate(31);
        long position=0;
        while(true){
          buffer.clear();
          int n=channel.read(buffer,position).get(5,TimeUnit.SECONDS);
          requests++;
          if(n<0)break;
          if(n==0)continue;
          position+=n;
          buffer.flip();
          byte[] chunk=new byte[buffer.remaining()];
          buffer.get(chunk);
          result.write(chunk);
        }
      }
      System.out.println("bytes="+result.size());
      System.out.println("multiple-requests="+(requests>1));
      System.out.println("data-matches="+Arrays.equals(original,result.toByteArray()));
    }finally{Files.deleteIfExists(file);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AsyncChunkedReadDemo.java
java AsyncChunkedReadDemo
```

**stdout đã kiểm thử:**

```text
bytes=2500
multiple-requests=true
data-matches=true
```

Demo tạo 2.500 bytes ASCII và đọc bằng buffer chỉ có 31 bytes, nên phải đọc nhiều lần. Các lần `get` trong loop **đồng bộ hóa tại completion**, nhưng mỗi thao tác I/O được tạo bởi API bất đồng bộ.

**Không bê nguyên `ByteArrayOutputStream` sang file vài GiB**: kết quả đang tích lũy toàn bộ file vào RAM, phù hợp demo có 2.500 bytes. Với file lớn, hãy stream chunks vào parser, checksum, sink hoặc một pipeline có backpressure. Với nguồn không tin cậy, áp dụng quota số bytes và giới hạn thời gian xử lý.

## 9. Thread pool và executor: quản lý completion dispatch

Mỗi `AsynchronousFileChannel` gắn với một thread pool để xử lý sự kiện/dispatch completion handlers. Khi không cung cấp executor, nó dùng **default thread pool phụ thuộc implementation**, có thể được chia sẻ bởi các channels.

Overload cho phép chỉ định executor:

```java
AsynchronousFileChannel ch = AsynchronousFileChannel.open(
        file,
        Set.of(StandardOpenOption.READ),
        executor);
```

Đây là **snippet**: `executor` là `ExecutorService`, cần import. Việc tạo executor riêng có giá trị khi muốn **kiểm soát tài nguyên** và trách nhiệm đóng; không phải mặc định tốt nhất cho mọi yêu cầu.

Theo JavaDoc, executor dùng cho file channel nên hỗ trợ queue không bị giới hạn kích thước theo cách executor xử lý I/O events, và không chạy tasks trên chính caller thread của `execute`. Cấu hình executor cần chú ý **bản chất implementation-specific của các tác vụ I/O**. Không dùng `CallerRunsPolicy` rồi coi như không ảnh hưởng semantics; không shutdown executor **khi channel còn mở**, vì hành vi khi đó không được chỉ định rõ.

**Quy tắc thực tế:** nếu dùng một pool riêng, tạo pool trước, mở channel với pool, đợi các operations cần thiết hoàn tất, đóng channel, rồi mới shutdown pool. Không tạo một pool mới cho từng byte/từng read nhỏ.

### 9.1. Ví dụ runnable: callback với executor riêng

Lưu thành `AsyncExecutorDemo.java`:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.*;
import java.nio.file.*;
import java.util.Set;
import java.util.concurrent.*;
public class AsyncExecutorDemo {
  public static void main(String[] args)throws Exception{
    Path file=Files.createTempFile("async-executor-", ".txt");
    ExecutorService pool=Executors.newFixedThreadPool(2);
    try{
      Files.writeString(file,"Z",StandardCharsets.UTF_8);
      try(AsynchronousFileChannel channel=AsynchronousFileChannel.open(
              file,Set.of(StandardOpenOption.READ),pool)){
        ByteBuffer target=ByteBuffer.allocate(1);
        CompletableFuture<String> done=new CompletableFuture<>();
        CompletionHandler<Integer,String> handler=new CompletionHandler<>(){
          public void completed(Integer n,String tag){
            if(n<0){done.completeExceptionally(new IOException("EOF"));return;}
            if(n==0){channel.read(target,0L,tag,this);return;}
            target.flip();
            done.complete(tag+":"+StandardCharsets.UTF_8.decode(target));
          }
          public void failed(Throwable error,String tag){
            done.completeExceptionally(error);
          }
        };
        channel.read(target,0L,"file",handler);
        System.out.println("callback="+done.get(5,TimeUnit.SECONDS));
      }
    }finally{
      pool.shutdown();
      if(!pool.awaitTermination(5,TimeUnit.SECONDS))pool.shutdownNow();
      Files.deleteIfExists(file);
    }
    System.out.println("pool-shutdown="+pool.isShutdown());
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AsyncExecutorDemo.java
java AsyncExecutorDemo
```

**stdout đã kiểm thử:**

```text
callback=file:Z
pool-shutdown=true
```

Ý nghĩa:

- `Executors.newFixedThreadPool(2)` tạo pool có queue phục vụ tasks theo implementation thông thường.
- `Set.of(StandardOpenOption.READ)` chỉ rõ mode đọc của channel.
- Callback hoàn tất `CompletableFuture<String>` để demo có thể chờ kết quả và test stdout.
- `attachment` là `"file"`, dùng như correlation tag.
- File chứa **một byte**; nếu read trả 0, handler thử lại. Trên filesystem bình thường, read nhận 1 byte.
- Channel đóng **trước** khi executor shutdown, và file tạm được xóa sau đó.

**Cảnh báo:** `CompletableFuture` trong ví dụ là một cầu nối do ứng dụng tự xây. `AsynchronousFileChannel` **không có overload chuẩn trực tiếp trả `CompletableFuture`**; Future mặc định của channel là `Future<Integer>`. Khi thiết kế production, cần quản lý cancel, timeout, trạng thái lỗi và trách nhiệm close rõ ràng.

### 9.2. Kích thước pool không đồng nhất số I/O thực sự chạy song song

Đặt pool size 32 không cam kết 32 lần đọc disk cùng lúc. Môi trường có giới hạn device bandwidth, filesystem locks, OS queue depth, storage locality và cơ chế executor. Thậm chí quá nhiều concurrent I/O có thể gây thrashing/latency cao.

Cần đo:

- Throughput bytes/s, operations/s theo từng loại workload.
- P50/P95/P99 latency, queue wait, timeout rate.
- Số requests đang chờ và kích thước buffer đang giữ.
- Số threads/CPU/RAM, direct memory.
- Số file handles, open channels và giới hạn OS.
- Error rate: access denied, closed channel, quota, I/O exception.
- Sự khác biệt giữa local SSD, HDD, mounted network FS và virtualized storage.

**Đừng lập trình một request vô hạn mới mỗi khi callback trả 0** trong production. Phải có deadline/backoff và cơ chế backpressure phù hợp.

## 10. File locks: AsynchronousFileChannel không chỉ đọc/ghi

Bên cạnh đọc/ghi, channel cung cấp API khóa vùng file:

- `lock()`: bắt đầu lấy **exclusive lock** và trả `Future<FileLock>`.
- `lock(position,size,shared)`: lấy khóa cho một vùng chỉ định.
- `lock(attachment,handler)` và overload khác: báo kết quả qua completion handler.
- `tryLock()`/`tryLock(...)`: thử ngay, có thể trả `null` nếu khóa bị process khác chiếm.
- `FileLock.release()`: nhả khóa đã lấy.
- Đóng channel có thể khiến khóa được release theo contract/provider.

**Locks không phải cơ chế nghiệp vụ tuyệt đối.** Trên một số môi trường, khóa có thể mang tính advisory; process khác không tuân thủ locking protocol có thể không bị giới hạn như ứng dụng kỳ vọng. Không dùng file lock làm phương tiện thay thế authorization, database transaction hoặc data validation.

### 10.1. Ví dụ runnable: lấy và nhả một exclusive lock

Lưu thành `AsyncFileLockDemo.java`:

```java
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.FileLock;
import java.nio.file.*;
import java.util.concurrent.TimeUnit;
public class AsyncFileLockDemo {
  public static void main(String[] args)throws Exception {
    Path file=Files.createTempFile("async-lock-", ".bin");
    try{
      try(AsynchronousFileChannel channel=AsynchronousFileChannel.open(
              file,StandardOpenOption.READ,StandardOpenOption.WRITE)){
        FileLock lock=channel.lock().get(5,TimeUnit.SECONDS);
        System.out.println("acquired="+lock.isValid());
        lock.release();
        System.out.println("released="+!lock.isValid());
      }
    }finally{Files.deleteIfExists(file);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AsyncFileLockDemo.java
java AsyncFileLockDemo
```

**stdout đã kiểm thử trên filesystem hỗ trợ file lock:**

```text
acquired=true
released=true
```

Đây là tệp tạm mới chỉ do một process demo sở hữu, nên không xảy ra contention. Trên filesystem/provider không hỗ trợ semantics khóa như yêu cầu, thao tác có thể thất bại: một test portable không nên tự động báo “Java lỗi”, mà cần kiểm tra feature/permission và báo loại exception đúng.

**`OverlappingFileLockException`** có thể xuất hiện nếu một vùng đã bị khóa hoặc đang chờ bị khóa bởi chính JVM theo contract. Nếu bạn muốn hai workers ghi các vùng khác nhau, khóa vùng cũng phải được định nghĩa, không cứ lấy exclusive lock toàn file cho mọi yêu cầu.

## 11. size(), truncate() và force() không phải API trả Future

Tên class `AsynchronousFileChannel` **không biến mọi phương thức thành async**:

```java
long length = channel.size();
channel.truncate(100L);
channel.force(true);
```

Đây là snippet; `channel` cần đang mở, `truncate` cần writable channel, `force` có thể tốn thời gian. Các lời gọi trên không trả Future. `size()` là trạng thái **tại thời điểm quan sát**, có thể thay đổi sau đó nếu writer khác đang hoạt động.

- `size()`: hữu ích khi lập kế hoạch chunks nhưng không phải snapshot bất biến.
- `truncate(long newSize)`: rút ngắn file khi `newSize` nhỏ hơn size; không phải operation để tự động kéo dài theo kích thước mới.
- `force(boolean metadata)`: yêu cầu flush cập nhật theo contract; với local storage có bảo đảm được mô tả trong JavaDoc, với remote storage không có cùng bảo đảm.
- `tryLock()` là một operation trả ngay/throw, **không** chờ asynchronously như `lock()`.

Cẩn thận khi có **outstanding writes**: nếu bạn gọi `force` trước khi các Futures hoàn tất, không được suy rằng những writes chưa hoàn tất đều đã được force. Thiết kế bước commit rõ: hoàn tất writes -> force (nếu policy yêu cầu) -> close -> công bố kết quả.

**Mở rộng file bằng ghi ở offset lớn hơn EOF** được hỗ trợ theo contract, nhưng bytes trong “lỗ hổng” giữa EOF trước đó và vùng mới ghi có giá trị **không được chỉ định**. Đừng dựa vào chúng là zero trên mọi provider nếu cần định dạng dữ liệu xác định.

## 12. Lỗi thường xảy ra ở hai thời điểm khác nhau

Một số lỗi được phát hiện **ngay khi gọi** `read/write`; các lỗi I/O khác được báo khi operation **hoàn tất bất đồng bộ**.

| Tình huống | Nơi lỗi có thể xuất hiện |
| --- | --- |
| `position < 0` | `IllegalArgumentException` tại lúc gọi `read/write` |
| `read` vào read-only buffer | `IllegalArgumentException` tại lúc gọi |
| `read` trên channel chỉ WRITE | `NonReadableChannelException` |
| `write` trên channel chỉ READ | `NonWritableChannelException` |
| File bị xóa, mất quyền hoặc lỗi I/O sau khi request đã tạo | `Future.get()` có thể ném `ExecutionException` với cause; hoặc `handler.failed(Throwable,attachment)` |
| Wait timeout | `Future.get(timeout,unit)` ném `TimeoutException` |
| Thread chờ bị interrupt | `InterruptedException` |
| Future bị cancel | `CancellationException` khi nhận kết quả, theo trạng thái Future |
| Channel bị đóng khi operation đang chờ | Có thể nhận `AsynchronousCloseException`; phải xem thông tin báo lỗi |
| Không hỗ trợ async channel/open option | `UnsupportedOperationException` trong lúc mở theo provider |

**Không coi `Future.get()` ném `ExecutionException` là root cause.** Hãy xem `getCause()`, ví dụ `IOException`. Nếu ở callback, xử lý `failed` và chuyển trạng thái nghiệp vụ, tránh log rồi quên pending job mãi mãi.

### 12.1. Ví dụ runnable: lỗi offset âm và mode không cho ghi

Lưu thành `AsyncArgumentValidationDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.NonWritableChannelException;
import java.nio.file.*;
public class AsyncArgumentValidationDemo {
  public static void main(String[] args)throws Exception{
    Path file=Files.createTempFile("async-args-", ".txt");
    try{
      Files.writeString(file,"X");
      try(AsynchronousFileChannel channel=AsynchronousFileChannel.open(
              file,StandardOpenOption.READ)){
        try{
          channel.read(ByteBuffer.allocate(1),-1L);
          System.out.println("negative-rejected=false");
        }catch(IllegalArgumentException ex){
          System.out.println("negative-rejected=true");
        }
        try{
          channel.write(ByteBuffer.wrap(new byte[]{1}),0L);
          System.out.println("write-rejected=false");
        }catch(NonWritableChannelException ex){
          System.out.println("write-rejected=true");
        }
      }
    }finally{Files.deleteIfExists(file);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AsyncArgumentValidationDemo.java
java AsyncArgumentValidationDemo
```

**stdout đã kiểm thử:**

```text
negative-rejected=true
write-rejected=true
```

Hai lỗi trên được phát hiện **ngay lúc gọi** operation trong môi trường kiểm thử, không cần chờ `Future.get()`. Điều đó cho thấy `AsynchronousFileChannel` không làm mọi lỗi chuyển sang callback.

**Đừng catch một `RuntimeException` chung rồi xem đó là “I/O chưa sẵn sàng”.** Các loại `IllegalArgumentException` và `NonWritableChannelException` thường báo bug trong precondition hoặc cấu hình mở channel; retry mà không sửa lỗi không giúp gì.

## 13. Timeout, cancellation và đóng channel đang chờ I/O

Khi worker gọi `Future.get(5, SECONDS)` và nhận `TimeoutException`, chỉ có **lời chờ** hết hạn. Chưa thể kết luận operation I/O đã kết thúc. Bạn cần một chính sách:

1. Theo dõi Future và giữ `ByteBuffer` còn hợp lệ cho đến khi operation thật sự kết thúc/có bảo đảm cleanup.
2. Nếu quyết định cancel, hiểu `Future.cancel(...)` có semantics/caveats của implementation; không tự động reuse buffer ngay chỉ vì đã yêu cầu cancel.
3. Nếu đóng channel để shutdown, outstanding operations có thể thất bại với `AsynchronousCloseException` theo contract.
4. Khi yêu cầu ngừng service, ngăn requests mới, điều phối tasks đang chờ và close trong một bước có ownership rõ.
5. Bảo đảm callback/worker không sử dụng buffer hoặc channel sau khi owner đã giải phóng tài nguyên không phù hợp.

### 13.1. Không đặt một lịch close quá sớm

Sai về vòng đời:

```java
Future<Integer> pending;
try (AsynchronousFileChannel channel =
        AsynchronousFileChannel.open(file, StandardOpenOption.READ)) {
    pending = channel.read(buffer, 0L);
}
// channel đã đóng, còn pending chưa chắc hoàn thành.
int n = pending.get();
```

Đây là snippet minh họa lỗi, không phải runnable program. Giải pháp: đợi operation hoàn tất **trong scope channel còn mở**, hoặc trao ownership channel rõ ràng cho một lifecycle manager đến khi callback/processing kết thúc.

**Không mặc định sleep vài mili giây trước close sẽ đủ.** Trễ I/O không có giới hạn cố định, nhất là network storage, HDD, tải hệ thống hoặc lỗi thiết bị.

### 13.2. InterruptedException và xử lý ở boundary

Nếu code bắt `InterruptedException` khi chờ:

```java
try {
    return pending.get(timeout, unit);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw ex;
}
```

Đây là snippet áp dụng tại boundary có checked exceptions phù hợp. Restore interrupt flag khi bạn chuyển/propagate lỗi, và phải đảm bảo channel/buffer đang chờ được dọn/đóng theo policy. Không nuốt interrupt rồi loop vô hạn chỉ để tiếp tục xử lý.

### 13.3. Callback có thể được gọi trên thread nào?

JavaDoc cam kết completion handler chạy bằng thread trong pool liên kết với channel; nếu I/O hoàn tất ngay và initiating thread cũng đang thuộc pool, callback **có thể** chạy trực tiếp trên initiating thread. Vì vậy:

- Không dựa vào callback luôn chạy trên “một background thread mới”.
- Không dựa vào thứ tự completion handlers bằng thứ tự lời gọi khởi tạo.
- Không thao tác trực tiếp UI thread-only object từ callback nếu framework yêu cầu event thread riêng.
- Không gọi một thao tác blocking kéo dài bên trong callback khi có thể enqueue sang worker riêng.
- Để callback xử lý failure rõ ràng và kết thúc state của request đúng một lần.

## 14. Đọc/ghi đồng thời: an toàn luồng không đồng nghĩa an toàn dữ liệu

Theo JavaDoc, channel **safe for use by multiple concurrent threads**. Điều này nghĩa implementation của channel cung cấp các bảo đảm thread-safety cho các methods của nó; **không** có nghĩa:

- Mọi shared `ByteBuffer` dùng bởi các operations là thread-safe.
- Hai writes chồng lấp tạo nội dung cuối có thứ tự được định nghĩa.
- Một read đang chạy nhìn thấy snapshot nhất quán nếu writer đang sửa cùng vùng.
- File size hoặc attributes không đổi giữa các calls.
- Khi một callback hoàn tất thì một callback khác đã chạy trước đó.
- Có thể close channel bất kỳ lúc nào mà vẫn cam kết tất cả outstanding operations thành công.
- `Future.get()` trên nhiều requests sẽ thu kết quả đúng thứ tự các bytes khi offsets đã đặt sai.

**Mẫu tốt cho đọc chia đoạn:**

1. Ghi lại một file identity/version hoặc yêu cầu producer đã publish immutable file.
2. Chia [offset, length] thành các vùng **không chồng lấp**.
3. Dùng buffer riêng cho mỗi operation đang chờ.
4. Có một giới hạn trên số request/buffers pending.
5. Mỗi operation có status, timeout/retry policy và byte count đã hoàn tất.
6. Chỉ parse/merge khi **tất cả chunks cần thiết đã hoàn tất** và được đặt lại đúng thứ tự offset.
7. Nếu file đổi version trong lúc đọc, discard/restart theo policy.

**Mẫu tốt cho ghi chia đoạn:**

1. Một coordinator cấp offset riêng cho từng chunk.
2. Ghi chunk vào vùng đã cấp, xử lý partial writes.
3. Không đọc file cuối như “hoàn chỉnh” trước khi các writes đã thành công.
4. Verify checksum/length/schema.
5. `force`/close/publish theo durability policy, nếu cần.
6. Ghi trạng thái idempotency/transaction tại downstream.
7. Đừng cho hai writers cùng nhận offset bằng việc cả hai đọc `channel.size()` rồi tự append: đó là race.

## 15. Có cần AsynchronousFileChannel cho mọi thao tác file?

**Không.** Chọn API theo bài toán, kích thước dữ liệu, số lượng công việc và khả năng vận hành.

| Tình huống | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| Đọc một file cấu hình nhỏ lúc startup | `Files.readString` hoặc `Files.readAllBytes` với giới hạn | Đơn giản, dễ xử lý lỗi; không cần callback |
| Đọc tuần tự một file lớn | `FileChannel` hoặc buffered/streaming I/O | Code dễ theo dõi; đôi khi đủ throughput |
| Copy một file từ nơi này sang nơi khác | `Files.copy` hoặc `FileChannel.transferTo/transferFrom` khi phù hợp | API copy/transfer chuyên dụng |
| Nhiều reads ở offsets khác nhau, cần overlap với công việc khác | `AsynchronousFileChannel` | I/O completion-based và positional |
| Ghi nhiều chunks độc lập vào một file | `AsynchronousFileChannel` cùng coordinator | Không có shared cursor, từng chunk có vị trí |
| Xử lý nhiều request đồng thời đọc các file khác nhau | Cân nhắc asynchronous file I/O, bounded workers hoặc API blocking phù hợp | Cần benchmark và quản lý tài nguyên |
| Xử lý socket bất đồng bộ | `AsynchronousSocketChannel` hoặc I/O networking framework | Khác mô hình file-channel |
| Tự động append log theo thứ tự | Một writer phối hợp, `FileChannel`/logging framework | Cần thứ tự và atomicity nghiệp vụ |
| Một thao tác đọc rồi lập tức `Future.get()` | Có thể dùng API đồng bộ | Async wrapper không chắc thêm lợi ích |
| File trên ZIP/custom provider không hỗ trợ async channel | API `Files`/`FileSystem` phù hợp provider | Không suy mọi provider đều cho `AsynchronousFileChannel.open` |

### 15.1. Vai trò của FileChannel vẫn rất quan trọng

`FileChannel` không phải API lỗi thời. Nó có `read/write` đồng bộ, positional variants, map, transfer, locks và các phương thức hữu ích. `AsynchronousFileChannel` không có toàn bộ phương thức tiện ích của `FileChannel` như mapping hoặc transfer-to.

Chọn chúng theo **yêu cầu concurrency và processing model** chứ không theo giả định rằng cái tên “Asynchronous” là phiên bản thay thế luôn tốt hơn.

### 15.2. Virtual threads và CompletableFuture có thay thế AsynchronousFileChannel không?

Trong Java hiện đại, có nhiều cách tổ chức concurrency, ví dụ `CompletableFuture` (Java 8+) hoặc virtual threads ở các phiên bản Java mới hơn. Chúng **không làm semantics của `AsynchronousFileChannel` trở nên lỗi thời**:

- `CompletableFuture` là abstraction về completion/composition, không tự làm mọi file operation thành non-blocking I/O.
- Một công việc `Files.readString` chạy trong executor vẫn là **blocking file call trên worker** theo cách gọi API, dù thread khởi tạo không phải trực tiếp chờ.
- `AsynchronousFileChannel` là **API file I/O completion-based** được provider thực hiện theo contract.
- Virtual threads có thể giúp tổ chức nhiều tác vụ blocking code dễ hơn trên runtime hỗ trợ, nhưng vẫn cần throughput/resource benchmark và lifecycle đúng; không phải bằng chứng native async I/O ở tầng thiết bị.

Bài này thực hành trên **Java 17+**. Không dùng syntax hoặc API chỉ có trong phiên bản mới hơn làm điều kiện chạy các ví dụ, để nội dung cơ bản vẫn phù hợp với Java 17 và các LTS hiện đại.

## 16. Tác dụng trong các pipeline phổ biến

### 16.1. Upload/chunked storage

Một service nhận các chunks có offset và ID:

```text
Upload session
  ├── chunk A: offset=0,       size=4096
  ├── chunk B: offset=4096,    size=4096
  ├── chunk C: offset=8192,    size=2038
  └── commit when all chunks verified
```

`AsynchronousFileChannel.write(buffer, offset)` là một primitive phù hợp vì **offset do coordinator quản lý**. Nhưng phải:

- Validate offset/length tránh overlap sai.
- Chặn dữ liệu không thuộc session/tenant.
- Giới hạn pending bytes/number of futures.
- Xử lý partial writes, retries và duplicate chunks.
- Verify tổng length/checksum, rồi publish file.
- Tránh cho người đọc nhìn thấy file staging chưa hoàn chỉnh.

**Không coi completion của chunk C là completion của toàn upload**. Commit cần trạng thái tất cả các chunks.

### 16.2. Đọc index hoặc block có định vị

Nếu file có header, offset table và nhiều blocks, có thể đọc block ở những vị trí khác nhau bằng nhiều requests. Điều này tránh tranh chấp shared cursor và có thể giúp overlap I/O với parsing ở những hệ thống thích hợp.

Tuy nhiên, nếu file đang được writer sửa đồng thời, **không có snapshot consistent mặc định**. Nên dùng immutable publication/versioning hoặc khóa/giao thức mà các parties tuân thủ.

### 16.3. Batch file processing

Một batch xử lý hàng trăm tệp có thể khởi tạo một số reads song song. **Đừng mở cùng lúc hàng chục nghìn channels mà không có giới hạn**: mỗi channel/file handle, buffer và outstanding request tốn tài nguyên. Lên lịch bằng semaphore/bounded executor, set per-file quota và metrics.

### 16.4. Dữ liệu cần durability

Đối với dữ liệu tài chính/giao dịch:

1. Ghi file staging với identity/version.
2. Đợi mọi asynchronous writes thành công, kiểm tra size/hash.
3. Gọi `force(...)` theo chính sách local storage.
4. Đóng channel, xử lý lỗi close.
5. Publish bằng cơ chế filesystem phù hợp.
6. Ghi transaction/checkpoint idempotent ở tầng nghiệp vụ.
7. Tài liệu hóa giới hạn remote filesystem và các bảo đảm phục hồi sau crash.

**`AsynchronousFileChannel` tự nó không cung cấp transaction commit, atomic multi-file update hoặc database durability**.

## 17. Giới hạn và những vấn đề bảo mật

Một tác vụ asynchronous nhận `Path` từ client hoặc một file chưa tin cậy vẫn có đầy đủ các nguy cơ I/O:

- **Path traversal** bằng `../` hoặc đường dẫn tuyệt đối không mong muốn.
- **Symlink/TOCTOU:** path đã kiểm tra có thể bị thay giữa lúc check và lúc mở; ancestor directory có thể là symlink.
- **Permission/ACL:** process không có quyền mở file hoặc storage có policy riêng.
- **Resource exhaustion:** buffer quá lớn, quá nhiều outstanding operations, quota/handle limit.
- **Malicious content:** dữ liệu lớn bất thường, binary malformed, archive bomb khi file được parser downstream sử dụng.
- **Concurrent mutation:** file bị truncate/recreate hoặc writer thay thế bytes khi reader đang đọc.
- **Disclosure:** log đường dẫn/cause/buffer có thể lộ tên file hoặc dữ liệu riêng tư.

**Giải pháp nhiều lớp:** chỉ mở dưới root do ứng dụng quản lý, cấp quyền tối thiểu, xác nhận loại file và ownership phù hợp, không theo symlink tùy ý, giới hạn I/O inflight, validate bytes/schema, tách staging/published data và xử lý exceptions theo chính sách bảo mật.

Một phép `Path.normalize().startsWith(root)` **chỉ kiểm tra lexical path**, không bảo vệ đầy đủ trước symlink ở ancestor hoặc thay đổi đồng thời. Không dùng nó làm bằng chứng sandbox tuyệt đối.

## 18. Testing: làm thế nào tránh các bài test không ổn định?

Với asynchronous I/O, những cách test dưới đây thường **không hợp lệ**:

- `Thread.sleep(10)` rồi giả định callback đã hoàn tất.
- Assert callback A luôn chạy trước callback B.
- Assert một read luôn điền đầy buffer.
- Assert file read luôn trả bytes giống snapshot nếu test đang ghi đồng thời.
- Assert callback chạy trên một thread tên cố định.
- Assert chỉ cần executor nhiều threads là thao tác đĩa nhanh hơn.
- Assert timeout đồng nghĩa I/O đã bị cancel.
- Assert lock luôn được hỗ trợ trên mọi filesystem/provider.
- Assert file trong `%TEMP%` đại diện cho network mount sản phẩm sẽ triển khai.

**Chiến lược kiểm thử tốt:**

1. Tạo file tạm chỉ thuộc sở hữu test và dùng nội dung có bytes xác định.
2. Dùng `Future.get(timeout)` hoặc `CountDownLatch.await(timeout)` với deadline thực tế, không ngủ tùy ý.
3. Đọc/ghi theo **số bytes thực nhận**, không giả định short transfer là error.
4. Kiểm tra data cuối cùng (bytes/hash) và file position, không kiểm tra callback arrival order.
5. Tách test pure logic/offset coordinator khỏi integration test trên storage thật.
6. Đối với race, tạo executor/test harness có điều phối rõ ràng thay vì dựa vào scheduling may mắn.
7. Với file locking và POSIX/ACL, test trên filesystem mục tiêu và có chính sách skip/fail được định nghĩa.
8. Đảm bảo channel đóng và temporary files được xóa kể cả khi test ném exception.
9. Với throughput, benchmark nhiều iterations/warmup, file sizes và loại storage, không dùng stdout demo làm benchmark.
10. Trong CI, giữ rõ kết quả lỗi do environment khác với lỗi thiết kế callback/buffer.

### 18.1. Biên dịch toàn bộ ví dụ

Các class ở từng mục là **chương trình độc lập**, mỗi class nằm trong một file đúng tên. Có thể biên dịch như sau trong thư mục chứa các file:

```bash
javac -encoding UTF-8 -Xlint:all AsyncFutureReadDemo.java
javac -encoding UTF-8 -Xlint:all AsyncFutureWriteDemo.java
javac -encoding UTF-8 -Xlint:all AsyncCompletionHandlerDemo.java
javac -encoding UTF-8 -Xlint:all AsyncPositionalReadsDemo.java
javac -encoding UTF-8 -Xlint:all AsyncChunkedReadDemo.java
javac -encoding UTF-8 -Xlint:all AsyncExecutorDemo.java
javac -encoding UTF-8 -Xlint:all AsyncFileLockDemo.java
javac -encoding UTF-8 -Xlint:all AsyncArgumentValidationDemo.java
```

Rồi chạy một class cụ thể:

```bash
java AsyncFutureReadDemo
```

Không cần thêm dependency Maven/Gradle cho các ví dụ này; chúng dùng JDK 17+ và filesystem mặc định. Các thao tác khóa tệp và file I/O thật vẫn phụ thuộc quyền/filesystem.

## 19. Các lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| Nghĩ `AsynchronousFileChannel` là `FileChannel` chạy nhanh hơn | Không có current file position và outcome timing khác | Hiểu positional I/O, Future/handler và benchmark |
| Gọi `future.get()` ngay rồi tuyên bố thread không block | `get` có thể chặn caller | Chồng lấp công việc hoặc callback khi cần |
| Đóng channel ngay sau `write` | I/O chưa chắc hoàn tất | Đợi tất cả Futures/callbacks rồi close |
| Dùng lại một `ByteBuffer` trước completion | Data race/undefined contents | Buffer riêng cho pending operations |
| Dùng cùng buffer ở hai reads đồng thời | Concurrent mutation buffer | Một buffer/mỗi request; tái sử dụng sau completion |
| Dùng một offset `0` cho mọi write chunk | Ghi chồng và sai dữ liệu | Tăng offset theo bytes đã hoàn tất |
| Dùng số bytes yêu cầu làm số bytes thực tế | Read/write có thể partial | Kiểm tra `n` và tiếp tục khi cần |
| Quên `flip()` sau read | Consumer đọc từ sai vị trí/limit | Dùng đúng vòng đời ByteBuffer |
| Coi `n==0` là EOF | EOF là `-1` đối với read phù hợp | Phân biệt 0 và -1 |
| Tin callback sẽ theo thứ tự khởi tạo | API không cam kết completion order | Định danh offset/request và merge đúng thứ tự |
| Coi multi-thread safe channel = safe shared buffer | Hai mức an toàn khác nhau | Synchronize hoặc tránh chia sẻ buffer |
| Gọi `force` khi writes còn pending | Những writes đó chưa chắc đã ghi xong | Hoàn tất writes trước force |
| Tắt executor khi channel còn mở | Behavior không được định nghĩa rõ | Close channel rồi shutdown executor |
| Parse file trong completion handler lâu | Có thể chiếm thread pool xử lý completions | Giao việc nặng sang worker riêng |
| Dựa vào `Future.cancel` như cam kết operation đã ngừng | Cancellation có giới hạn | Thiết kế lifecycle và tránh reuse buffer sớm |
| Tin timeout chắc chắn nghĩa operation thất bại | Timeout có thể chỉ là chờ quá hạn | Theo dõi state/cancel/close theo policy |
| Bắt `ExecutionException` mà bỏ cause | Mất root cause I/O | Kiểm tra `getCause()` |
| Coi position là số ký tự UTF-8 | Offset tính bằng **byte** | Encode trước và quản lý byte positions |
| Dùng APPEND với async channel như FileChannel | Không có shared current position | Cấp phát offset có synchronization |
| Tin file metadata là snapshot bất biến | Writer có thể thay file | Versioning hoặc immutable publication |
| Đọc vô hạn file chưa tin cậy vào RAM | Memory exhaustion | Chunk streaming, quotas/backpressure |
| Nghĩ file locks làm mọi writers phải hợp tác | Lock semantics có thể advisory/provider-specific | Thỏa thuận protocol và test trên target FS |
| Dùng async API cho một file nhỏ mà không cần concurrency | Tăng complexity | `Files.readString` hoặc `FileChannel` |
| Tin mọi provider hỗ trợ async file channels | Optional operation | Feature test, xử lý UnsupportedOperationException |

## 20. Checklist code review

1. Bài toán thật sự cần **completion-based file I/O** hay một API đồng bộ đơn giản đủ rồi?
2. Có chọn đúng `AsynchronousFileChannel` thay vì nhầm với `AsynchronousSocketChannel` không?
3. Có nhớ **không có current position**, offset phải truyền mỗi lần không?
4. Mọi offset đều không âm và được tính bằng **byte** chưa?
5. Tùy read/write, channel đã mở với đúng `READ`/`WRITE` chưa?
6. Nếu tạo file, có chính sách `CREATE`/`CREATE_NEW` và xử lý collision không?
7. Có phân biệt `Future<Integer>` và `CompletionHandler<Integer,A>` không?
8. Có hiểu `get()` vẫn block khi result chưa sẵn không?
9. Có xử lý partial read/write bằng `n` thật, không dùng requested count không?
10. Có phân biệt EOF `-1` với lần đọc có `0` bytes không?
11. Mọi ByteBuffer đang pending có ownership rõ và không bị sửa sớm không?
12. Có `flip/clear/compact` đúng giai đoạn không?
13. Với Unicode text, có quản lý charset/decoder qua chunks không?
14. Có cấm nhiều writers cùng offset overlap ngoài policy không?
15. Có thực sự chỉ commit sau khi tất cả chunks cần thiết hoàn tất không?
16. Với handler, có xử lý cả `completed` và `failed` không?
17. Callback có tránh block dài/giữ lock phức tạp không?
18. Attachment có quản lý thread-safety khi mutable không?
19. Có executor riêng không? Có giữ nó sống đến sau khi close channel không?
20. Có giới hạn số operations/buffers/channels đang chờ không?
21. Có timeout/deadline, interruption và cancellation policy không?
22. Có xử lý `ExecutionException.getCause()`, `AsynchronousCloseException` và I/O failures không?
23. Có kiểm tra tính năng provider/permissions của target filesystem không?
24. Có đánh giá `size`/`truncate`/`force` là calls trực tiếp, không Future không?
25. Nếu dùng `FileLock`, có hiểu lock semantics và phối hợp với processes khác không?
26. Có đo throughput/latency ở storage thực tế, tránh kết luận “async luôn nhanh” không?
27. Có giữ file/buffers/streams còn sống đến khi completion và dọn trong `finally`/TWR không?
28. Nếu dữ liệu nhạy cảm, có root policy, ACL/permissions, validate, quotas và symlink controls không?
29. Có code test không phụ thuộc callback arrival order hoặc số threads giả định không?
30. Có chọn đúng abstraction nếu mục tiêu là append tuần tự, transfer, memory map hoặc socket I/O không?

## 21. Bài tập

**Bài 1 — Nhận diện tính bất đồng bộ.** Chạy `AsyncFutureReadDemo` và chỉ ra chính xác dòng khởi tạo I/O, dòng đợi hoàn tất và dòng sử dụng bytes. Nếu di chuyển `get()` tới sau một công việc CPU ngắn, điều gì thay đổi về lịch thực thi?

**Bài 2 — Partial read.** Sửa buffer trong `AsyncFutureReadDemo` thành nhỏ hơn file rồi đọc theo nhiều chunks. Vì sao không được khẳng định một `read` duy nhất trả đúng số bytes yêu cầu?

**Bài 3 — Partial write.** Chạy `AsyncFutureWriteDemo` với nội dung 2.000 bytes. Kiểm tra số bytes ghi và tăng file offset đúng theo `n`. Đừng bỏ vòng `while(source.hasRemaining())`.

**Bài 4 — CompletionHandler.** Chạy `AsyncCompletionHandlerDemo`. Đổi attachment thành một record chứa ID và offset. Truyền lỗi qua `AtomicReference`/CompletableFuture thay vì chỉ in trong callback.

**Bài 5 — Nhiều offsets.** Chạy `AsyncPositionalReadsDemo` với 3 vùng bytes không chồng lấp. Lấy Futures theo thứ tự khác nhau nhưng ghép dữ liệu theo offset cho ra chuỗi gốc.

**Bài 6 — Buffer lifecycle.** Chạy `AsyncChunkedReadDemo` với `ByteBuffer.allocate(7)`. Giải thích sự khác nhau của `clear`, `flip`, `position`, `limit` và `remaining`.

**Bài 7 — Concurrency.** Viết coordinator phát tối đa bốn outstanding reads với buffer riêng, kết quả được ghi về một map theo offset. Không dựa vào thứ tự hoàn thành.

**Bài 8 — Executor.** Chạy `AsyncExecutorDemo` rồi thay pool size 2 thành 1, kiểm tra chức năng vẫn đúng. Benchmark riêng dưới tải đủ lớn thay vì suy tốc độ từ số threads.

**Bài 9 — File lock.** Chạy `AsyncFileLockDemo`. Mở hai channels và thử lấy khóa vùng chồng lấp để quan sát `OverlappingFileLockException` theo API; không khóa file thật của người khác.

**Bài 10 — Precondition.** Chạy `AsyncArgumentValidationDemo`. Thử đọc vào read-only `ByteBuffer` và phân biệt lỗi phát sinh lúc khởi tạo operation với lỗi trả về qua Future.

**Bài 11 — Timeout.** Mô phỏng I/O kết thúc chậm bằng một `CompletableFuture` test double thay vì cố làm đĩa thật chậm. Xây policy khi `get(timeout)` thất bại và giải thích vì sao không reuse buffer ngay.

**Bài 12 — Durability.** Thiết kế upload session: ghi chunks hoàn tất, force, close, verify, publish và ghi checkpoint. Nêu ranh giới giữa asynchronous I/O, atomic rename và transaction của ứng dụng.

**Bài 13 — Security.** File path do client gửi trỏ tới một symlink ngoài thư mục được phép. Thiết kế quyền tối thiểu, validate path/entry và chống TOCTOU; giải thích vì sao `normalize()` một mình chưa đủ.

**Bài 14 — Provider.** Thử mở `AsynchronousFileChannel` trên một filesystem ảo hoặc archive provider trong integration test, xử lý `UnsupportedOperationException` đúng chính sách. Không giả định mọi provider giống default filesystem.

**Bài 15 — Chọn API.** Với ba tình huống — cấu hình nhỏ, upload nhiều chunks và copy file lớn — hãy chọn giữa `Files`, `FileChannel` và `AsynchronousFileChannel`. Giải thích dựa trên thứ tự, resource ownership, độ phức tạp và nhu cầu concurrency.

## 22. Tổng kết

- **`AsynchronousFileChannel` là API hiện hành để đọc/ghi file theo completion-based I/O**; không phải phiên bản “luôn nhanh hơn” của `FileChannel`.
- **Mỗi `read/write` cần một file byte offset riêng; không có current position dùng chung.**
- Hai kiểu nhận kết quả là **`Future<Integer>`** và **`CompletionHandler<Integer,A>`**; `Future.get()` có thể block và callback cần xử lý cả thành công/lỗi.
- **ByteBuffer còn đang pending không được tái sử dụng hoặc sửa tùy tiện**. Số bytes chuyển có thể nhỏ hơn yêu cầu; read tới EOF trả `-1`.
- Có thể có nhiều read/write đang chờ, nhưng **thứ tự completion không được bảo đảm**; ghi vùng chồng lấp đòi phối hợp của ứng dụng.
- Channel dùng **thread pool** cho I/O events/completions; không có cam kết toàn bộ việc file I/O dùng native OS nonblocking hay tăng throughput tự động.
- `lock` có overload bất đồng bộ; **`size/truncate/force` là những calls trực tiếp**, không trả Future.
- **Close, timeout, cancellation, executor và locks** phải có ownership/lifecycle rõ ràng.
- Với các file nhỏ hoặc I/O đơn giản, `Files` hoặc `FileChannel` có thể dễ hiểu và phù hợp hơn.
- Luôn kiểm thử trên filesystem mục tiêu, xử lý I/O exceptions, bảo vệ path và giới hạn resources; phần bất đồng bộ không thay thế validation, transaction hoặc bảo mật.

## Tài liệu chính thức

- [AsynchronousFileChannel — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): các overload `open/read/write/lock/force`, thread pools, thứ tự completion và lifecycle.
- [CompletionHandler — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/CompletionHandler.html): callback `completed/failed` và attachment.
- [ByteBuffer — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): position, limit, flip, clear, direct/heap buffer.
- [Future — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): `get`, timeout, completion và cancellation.
- [FileChannel — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): so sánh chức năng đọc/ghi đồng bộ, transfer và mapping.
- [FileLock — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileLock.html): lock regions, release và giới hạn nền tảng.
- [StandardOpenOption — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardOpenOption.html): các options mở file.
- [Files — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): utilities, quyền filesystem và xử lý tệp.
