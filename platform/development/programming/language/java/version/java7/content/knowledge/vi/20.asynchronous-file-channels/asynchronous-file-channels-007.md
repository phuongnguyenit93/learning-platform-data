# Kênh tệp bất đồng bộ trong Java: Khóa vùng tệp và xử lý lỗi hoàn tất

## 1. Vấn đề thực tế: nhiều tiến trình cùng truy cập một tệp

Một ứng dụng Java lưu các bản ghi có kích thước cố định trong cùng tệp nhị phân `records.bin`. Tiến trình A đang cập nhật phần đầu file, trong khi một tiến trình khác có thể cũng đọc hoặc ghi file này. Việc tạo một `AsynchronousFileChannel` giúp chương trình **khởi tạo các thao tác I/O bất đồng bộ**, nhưng **không tự bảo đảm** rằng hai tiến trình không sửa cùng vùng byte hoặc các thao tác hoàn tất theo thứ tự mong muốn.

Khi cần giao thức phối hợp truy cập file với những chương trình khác, Java NIO.2 cho phép:

- Yêu cầu **khóa độc quyền (exclusive)** hoặc **khóa chia sẻ (shared)** trên một vùng byte cụ thể.
- Dùng `AsynchronousFileChannel.lock(...)` để yêu cầu khóa theo dạng **`Future<FileLock>`** hoặc **`CompletionHandler<FileLock,A>`**.
- Dùng `tryLock(...)` khi muốn **thử lấy khóa ngay**, không chờ lock của tiến trình khác được thả.
- Nhận biết lỗi xuất hiện **ngay tại lúc gọi phương thức** khác với lỗi của **thao tác hoàn tất bất đồng bộ**.
- Giữ và **giải phóng đối tượng `FileLock`** đúng vòng đời, kể cả khi callback hoặc tác vụ nghiệp vụ gặp lỗi.
- Xử lý timeouts, đóng channel, lỗi I/O, khóa chồng lấn, cancellation và giới hạn hệ điều hành.

Những API này đã có trong **Java 7**, vẫn còn được hỗ trợ trong các JDK hiện đại và không thuộc nhóm kiến thức đã lỗi thời. Chương trình minh họa trong bài dùng **JDK 17+**, biên dịch với `javac --release 17 -Xlint:all -Werror` và được kiểm thử thực tế.

**Tư tưởng quan trọng nhất:** khóa vùng tệp là một **hợp đồng phối hợp truy cập với các chương trình khác**, không phải một mutex tự động bảo vệ các thread trong cùng JVM, và cũng không phải một giao dịch ghi dữ liệu. Bạn phải xử lý **cả việc nhận kết quả thành công/thất bại** lẫn **vòng đời thả khóa**.

## 2. Vai trò của `AsynchronousFileChannel`, `FileLock` và `CompletionHandler`

| Thành phần | Vai trò | Giá trị thường gặp |
| --- | --- | --- |
| `AsynchronousFileChannel` | Channel đọc/ghi ở vị trí cụ thể và yêu cầu file lock theo mô hình bất đồng bộ | `open`, `read`, `write`, `lock`, `tryLock`, `close` |
| `FileLock` | Token đại diện cho một khóa trên vùng file đã lấy thành công | `position()`, `size()`, `isShared()`, `isValid()`, `release()` |
| `Future<FileLock>` | Đại diện cho kết quả sẽ có trong tương lai của yêu cầu `lock` | `get()`, `get(timeout,unit)`, `cancel()` |
| `CompletionHandler<FileLock,A>` | Nhận kết quả hoặc nguyên nhân thất bại khi thao tác lock hoàn tất | `completed(FileLock,A)`, `failed(Throwable,A)` |
| `attachment` | Dữ liệu ngữ cảnh do bên gọi truyền vào, trả lại nguyên dạng trong callback | Tên tác vụ, request ID, object chứa state |
| `OverlappingFileLockException` | Lỗi khóa chồng lấn trong cùng JVM hoặc có yêu cầu lock chồng lấn đang chờ | Thường được ném ngay khi gọi lock/tryLock |
| `ExecutionException` | Bao bọc lỗi của thao tác bất đồng bộ khi gọi `Future.get()` | Đọc `getCause()` để xác định lỗi gốc |

`AsynchronousFileChannel` không giữ một **current file position** dùng chung như một số cách dùng `FileChannel`: các thao tác read/write nhận **vị trí byte tường minh**. Khóa vùng tệp cũng nhận `position` và `size` theo byte; không dựa vào offset ký tự trong chuỗi Java.

### 2.1. Mở channel với quyền thích hợp

```java
import java.nio.channels.AsynchronousFileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path file = Path.of("records.bin");

try (AsynchronousFileChannel channel =
        AsynchronousFileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {
    // Yêu cầu khóa và thao tác file trong phạm vi này.
}
```

Đây là **mã minh họa trong phương thức có xử lý `IOException`**, giả sử file tồn tại và provider hỗ trợ asynchronous file channel. `Path.of` có từ Java 11; Java 7/8 có thể dùng `Paths.get`. Hai option READ và WRITE giúp ví dụ có thể yêu cầu khóa shared hoặc exclusive; tuy nhiên **provider và hệ điều hành có thể có giới hạn**.

Nếu chỉ mở channel với `READ` rồi yêu cầu khóa **exclusive**, phương thức lock thường ném `NonWritableChannelException`. Nếu chỉ có `WRITE` và muốn khóa **shared**, có thể ném `NonReadableChannelException`. Chọn open options theo loại khóa thực sự cần.

## 3. Khóa vùng tệp được xác định bằng byte offset và độ dài

Overload quan trọng:

```java
Future<FileLock> future =
        channel.lock(position, size, shared);
```

Ba tham số:

- `position`: vị trí bắt đầu tính từ **byte 0**, kiểu `long` và phải không âm.
- `size`: độ dài vùng khóa tính bằng **byte**, kiểu `long` và phải không âm.
- `shared`: `true` để yêu cầu shared lock; `false` để yêu cầu exclusive lock.

Với độ dài dương, có thể hình dung vùng là **nửa mở `[position, position + size)`**.

```text
Bytes:       0   1   2   3   4   5   6   7   8   9
Lock A:     [0--------------4)
Lock B:                     [4--------------8)
Lock C:             [2------5)
             A và B: không chồng lấn
             A và C: có chồng lấn ở các byte 2,3
```

Nếu lấy khóa A trên `[0,4)`, vùng bắt đầu tại `4` không chồng lấn vì **không có byte chung**. Nhưng vùng `[2,3)` chồng lấn A.

### 3.1. Vùng khóa có thể vượt cuối file

`FileLock` lưu **vùng được yêu cầu**, không nhất thiết chỉ những byte hiện đã tồn tại trong file. Một tệp dài 16 byte vẫn có thể yêu cầu khóa bắt đầu sau byte 16 nếu provider cho phép. Vì vậy không nên dùng `FileLock.size()` làm “kích thước hiện tại của file”.

Đây là lý do phân biệt:

- `channel.size()`: kích thước hiện tại của file (đơn vị byte), có thể thay đổi.
- `lock.position()`: byte bắt đầu của vùng khóa.
- `lock.size()`: kích thước **vùng khóa**, không phải kích thước file.
- `lock.isValid()`: trạng thái khóa còn giữ hiệu lực hay không.

### 3.2. Trường hợp `size == 0`

Với các overload `lock(position,size,shared)` hoặc `tryLock(position,size,shared)`, `size = 0` có nghĩa yêu cầu khóa **từ vị trí cho trước đến cuối file**, kể cả khi file về sau được mở rộng hoặc rút ngắn — **không** phải khóa vùng rỗng. Đây là điểm ít trực giác nhưng quan trọng theo hợp đồng API.

```java
Future<FileLock> tail =
        channel.lock(100L, 0L, false);
```

Đây là minh họa trong phương thức có `channel` đã mở WRITE. Không gọi `tail.get()` vô hạn trong luồng xử lý request nếu không có chính sách timeout; khi khóa lấy được, đối tượng `FileLock` phải được giải phóng.

### 3.3. Khóa toàn bộ file

`channel.lock()` tương đương yêu cầu **exclusive lock** trên vùng:

```java
channel.lock(0L, Long.MAX_VALUE, false);
```

Còn overload callback `channel.lock(attachment,handler)` tương đương khóa toàn bộ theo cấu hình đó. Khi yêu cầu lock toàn bộ file, hãy nhớ việc này có thể chặn các tiến trình hợp tác khác trong một thời gian dài; trong các hệ thống có concurrency tốt hơn, khóa vùng nhỏ có thể phù hợp hơn.

### 3.4. Giá trị tham số không hợp lệ

Java có thể ném `IllegalArgumentException` **ngay tại lúc gọi** nếu:

- `position < 0` hoặc `size < 0`.
- Tổng `position + size` không hợp lệ theo điều kiện API, ví dụ gây tràn phạm vi `long`.

Không lấy giá trị từ nguồn không tin cậy rồi đưa trực tiếp vào lock mà không xác minh. Có thể dùng `Math.addExact` nếu cần kiểm tra phép cộng trong code nghiệp vụ, nhưng vẫn phải áp dụng hợp đồng của lock đối với `size==0`.

## 4. Shared và exclusive: yêu cầu khóa khác nhau thế nào?

| Loại | `shared` | Điều kiện mở channel | Hợp đồng phối hợp thường gặp |
| --- | --- | --- | --- |
| **Exclusive** | `false` | Channel mở để **WRITE** | Ngăn chương trình hợp tác khác lấy khóa chồng lấn, cả shared lẫn exclusive |
| **Shared** | `true` | Channel mở để **READ** | Nhiều reader có thể lấy shared lock chồng lấn; writer exclusive sẽ phải đợi hoặc thất bại |
| **Không khóa** | Không gọi lock | Theo thao tác I/O | Không có cơ chế phối hợp từ file-lock API |

### 4.1. Shared lock không luôn được nền tảng hỗ trợ

Một số hệ thống không hỗ trợ shared file lock và có thể **chuyển yêu cầu shared thành exclusive**. Vì vậy sau khi lock hoàn tất, dùng `lock.isShared()` để biết **loại khóa thực tế được cấp**, thay vì giả định cứ truyền `shared=true` thì hệ điều hành nhất thiết cấp shared.

### 4.2. Khóa thường phải được coi như advisory

API file locking của Java ánh xạ sang cơ chế native của hệ điều hành. Có nơi khóa mang tính **advisory** — các chương trình phải tự tuân thủ giao thức. Có nơi khóa có thể tác động bắt buộc (**mandatory**) tới một số thao tác. Java khuyến nghị **lập trình theo mô hình advisory** để có hành vi nhất quán hơn giữa các nền tảng.

Điều này có nghĩa:

- File lock không phải tường bảo mật chống chương trình cố tình bỏ qua giao thức.
- File lock **không tự mã hóa** hoặc xác thực dữ liệu.
- Một ứng dụng khác không tuân theo cơ chế khóa vẫn có thể thay file trên nền tảng chỉ hỗ trợ advisory.
- Hành vi khóa trên network filesystem, shared storage hoặc mapped file có thể khác nhau.
- Kể cả có khóa, ứng dụng vẫn cần kiểm tra tính đúng đắn của byte đã đọc/ghi và xử lý lỗi I/O.

### 4.3. Không dùng khóa file để đồng bộ thread trong cùng JVM

Khóa tệp theo Java được giữ **trên danh nghĩa toàn bộ JVM**, không phải riêng từng `Thread`. Java cũng **không cho phép các file lock chồng lấn trên cùng một file trong một JVM**, kể cả chúng do các channel khác nhau tạo.

Do đó hai thread cùng JVM cần đồng bộ một biến hoặc một vùng byte **phải dùng cơ chế đồng bộ trong tiến trình** phù hợp, như `Lock`, `synchronized`, `Semaphore`, queue hoặc ownership model. File lock dùng khi cần phối hợp với những tiến trình khác, không phải thay thế mutex nội bộ.

## 5. Dạng `Future<FileLock>`: lấy và giải phóng kết quả

Overload:

```java
Future<FileLock> future = channel.lock(0L, 4L, false);
```

**Khởi tạo yêu cầu** lấy exclusive lock trên `[0,4)` và trả `Future<FileLock>`. Lúc phương thức trả về, không được mặc định khóa đã được lấy thành công.

Dùng `get` để chờ kết quả:

```java
import java.nio.channels.FileLock;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

Future<FileLock> future = channel.lock(0L, 4L, false);

FileLock lock = future.get(5, TimeUnit.SECONDS);
try (lock) {
    System.out.println("Locked region " + lock.position());
}
```

Đây là đoạn minh họa trong phương thức có xử lý **`InterruptedException`, `ExecutionException` và `TimeoutException`**, ngoài các lỗi đồng bộ có thể xuất hiện khi bắt đầu lock. Cú pháp `try (lock)` với biến đã khai báo có từ **Java 9**; trên Java 7 có thể dùng `try (FileLock held = future.get())` khi hình thức exception/khởi tạo phù hợp.

### 5.1. `Future.get()` khác `channel.lock()`

- `channel.lock(...)` có thể **trả nhanh một `Future`** khi thao tác còn pending.
- `future.get()` có thể **chặn luồng gọi** để đợi khóa.
- `future.get(timeout,unit)` cho phép giới hạn **thời gian chờ của bên gọi**, không tự bảo đảm thao tác bên dưới bị hủy khi hết hạn.
- `future.get()` trả `FileLock` nếu hoàn tất thành công.
- Nếu thao tác lock bất đồng bộ thất bại, `get()` ném **`ExecutionException`**, nguyên nhân nằm trong `getCause()`.
- Nếu thread đợi bị interrupt, `get()` có thể ném **`InterruptedException`**.
- Nếu Future bị hủy, `get()` có thể ném **`CancellationException`**.

### 5.2. Mẫu xử lý lỗi kết quả với `Future`

```java
try {
    FileLock lock = future.get(5, TimeUnit.SECONDS);
    try (lock) {
        useProtectedRegion(); // Hàm ứng dụng tự định nghĩa.
    }
} catch (java.util.concurrent.ExecutionException ex) {
    Throwable cause = ex.getCause();
    reportAsyncFailure(cause); // Hàm ứng dụng tự định nghĩa.
} catch (java.util.concurrent.TimeoutException ex) {
    reportTimeout(ex); // Hàm ứng dụng tự định nghĩa.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    reportCancellation(ex); // Hàm ứng dụng tự định nghĩa.
}
```

Đây là **mã minh họa chưa chạy độc lập** vì `future` và ba hàm xử lý nghiệp vụ phải được định nghĩa, đồng thời cần kiểm soát các lỗi có thể ném khi bắt đầu lock. Điểm học tập là **tách các loại lỗi**, không gom chúng thành một thông điệp “không thể mở file”.

### 5.3. Timeout không đồng nghĩa việc xin khóa đã kết thúc

`get(5,SECONDS)` ném `TimeoutException` chỉ nói **bên gọi đã chờ quá 5 giây**. Yêu cầu lock có thể vẫn đang chờ và về sau **lấy được khóa**. Nếu mã bỏ tham chiếu tới Future, khi operation hoàn tất có thể xuất hiện khóa không được release đúng cách.

Cần có chính sách ownership và cleanup:

1. Theo dõi yêu cầu còn pending.
2. Quyết định có gọi `future.cancel(...)` hay đóng channel theo lifecycle của riêng tác vụ đó.
3. Hiểu cancellation của asynchronous I/O phụ thuộc implementation; **không mặc định `cancel` hủy sạch native lock ngay lập tức**.
4. Bảo đảm nếu operation vẫn hoàn tất thành công sau một cuộc đua timeout/cancel, `FileLock` được nhận và giải phóng bởi thành phần thực sự sở hữu nó.
5. Tránh đóng channel dùng chung của các tác vụ khác chỉ để giải quyết một timeout cục bộ.

Đây là vấn đề **thiết kế vòng đời thực sự**, không thể được giải quyết bằng `catch (TimeoutException) { return; }` đơn giản khi có tài nguyên đã/đang được cấp.

## 6. Dạng `CompletionHandler<FileLock,A>`: nhận completion bất đồng bộ

API:

```java
channel.lock(
        position,
        size,
        shared,
        attachment,
        new CompletionHandler<FileLock, String>() {
            @Override
            public void completed(FileLock lock, String label) {
                // Sở hữu khóa vừa được cấp: xử lý và release.
            }

            @Override
            public void failed(Throwable error, String label) {
                // Thao tác lock hoàn tất thất bại.
            }
        });
```

Đây là **mã minh họa**, chưa độc lập vì `channel`, `position`, `size`, `shared` và xử lý thành công/thất bại phải được xác định. Kiểu `A` của `attachment` do ứng dụng chọn; ví dụ dùng `String` để đơn giản.

### 6.1. `completed(FileLock,A)`

Khi yêu cầu lock hoàn tất **thành công**, callback nhận một `FileLock`. Đối tượng đó là **tài nguyên cần release**, không phải chỉ một giá trị để in ra console.

Mẫu xử lý:

```java
@Override
public void completed(FileLock lock, String requestId) {
    try (FileLock owned = lock) {
        System.out.println("Lock acquired for " + requestId);
        // Có thể lên lịch phần xử lý đã được bảo vệ theo contract.
    } catch (IOException ex) {
        // Release/cleanup có thể thất bại: báo lỗi tới owner.
    }
}
```

Đây là phương thức minh họa nằm trong class triển khai `CompletionHandler<FileLock,String>`. Trong thực tế, nên đưa công việc dài sang luồng/tác vụ được quản lý, nhưng **không thả lock trước khi phần việc được bảo vệ thực sự hoàn tất**. Nếu callback chỉ đưa dữ liệu sang queue rồi release ngay, các thread xử lý sau đó không còn được bảo vệ bởi lock.

### 6.2. `failed(Throwable,A)`

Nếu **thao tác I/O bất đồng bộ** không lấy được lock do một lỗi được báo qua completion, callback:

```java
@Override
public void failed(Throwable error, String requestId) {
    System.err.println("Lock failed: " + requestId
            + ", type=" + error.getClass().getSimpleName());
    // Thông báo cho caller bằng CompletableFuture/queue/state phù hợp.
}
```

Đây là phương thức minh họa trong class callback. Vì `failed` nhận `Throwable`, hãy phân loại lỗi và chuyển nguyên nhân sang tầng quản lý tác vụ. Không chỉ in log rồi để caller chờ mãi vì chưa nhận được kết quả.

**Quan trọng:** `failed` không phải nơi duy nhất mọi lỗi có thể xuất hiện. Một số sai phạm đối số, mode channel hoặc xung đột khóa trong cùng JVM có thể được **ném đồng bộ ngay khi gọi `channel.lock(...)`**, trước khi callback được đăng ký thành công.

### 6.3. Callback chạy trên thread nào?

`AsynchronousFileChannel` gắn với một thread pool phục vụ completion handlers. Callback thường chạy trên thread thuộc pool liên quan; không nên giả định đó là thread đã gọi `lock`, thread xử lý HTTP request, hoặc một thread UI cố định.

Vì vậy:

- Các biến được chia sẻ giữa callback và caller cần cơ chế đồng bộ/thread-safe.
- Đừng chặn callback quá lâu vì có thể cản việc dispatch những completion khác.
- Không tự cập nhật giao diện người dùng từ callback nếu framework yêu cầu một UI thread riêng.
- Không dựa vào thứ tự các callback là đúng thứ tự khởi tạo operation.
- Khi dùng một pool tùy biến, chủ sở hữu phải quyết định lịch shutdown và xử lý quá tải.

### 6.4. Quản lý lỗi do **mã callback** tự ném

Nếu callback `completed` đã được gọi, rồi **mã ứng dụng trong callback** tự ném exception, điều đó **không tự bảo đảm** provider sẽ gọi `failed` lần nữa cho cùng operation. Callback phải có `try/finally` để release tài nguyên và chuyển lỗi theo kênh trạng thái của ứng dụng.

Trong chương trình kiểm thử của bài, callback dùng `CountDownLatch` và `AtomicReference` để:

- Cho thread điều phối biết callback đã chạy xong.
- Giữ kết quả hoặc nguyên nhân lỗi, kể cả lỗi phát sinh khi release.
- Không dựa vào thứ tự scheduler.
- Tránh phải chờ vô hạn bằng một thời hạn 5 giây.

## 7. Phân biệt lỗi khởi tạo yêu cầu và lỗi hoàn tất

Đây là phần thường gây bug nghiêm trọng nhất.

| Khi nào? | Ví dụ | Lỗi có thể xuất hiện ở đâu? |
| --- | --- | --- |
| **Ngay khi gọi `lock`** | `position < 0`, `size < 0`, tổng vùng không hợp lệ | `IllegalArgumentException` đồng bộ |
| **Ngay khi gọi `lock`** | Yêu cầu chồng lấn lock do JVM đã giữ/đang chờ | `OverlappingFileLockException` đồng bộ |
| **Ngay khi gọi `lock`** | Đòi exclusive mà channel không có WRITE | `NonWritableChannelException` đồng bộ |
| **Ngay khi gọi `lock`** | Đòi shared mà channel không có READ | `NonReadableChannelException` đồng bộ |
| **Sau khi đã khởi tạo thành công** | Native I/O/lock acquisition gặp lỗi | `CompletionHandler.failed(Throwable,A)` hoặc `Future.get()` bọc `ExecutionException` |
| **Trong khi đang chờ `Future.get()`** | Thread đang đợi bị ngắt | `InterruptedException` từ `get()` |
| **Trong khi đang chờ `Future.get(timeout)`** | Thời hạn đợi của caller hết | `TimeoutException` từ `get()` |
| **Future bị hủy** | Consumer gọi `get` trên Future đã cancel | `CancellationException` |
| **Đóng channel khi còn operation pending** | `channel.close()` trong lúc lock chưa hoàn tất | Operation bất đồng bộ có thể thất bại với `AsynchronousCloseException` |
| **Sau khi có `FileLock`** | `release`/`close` của lock gặp lỗi I/O | `IOException` ở thao tác giải phóng |

**Không nên viết**:

```java
channel.lock(position, size, false, requestId, handler);
// Và giả định handler.failed() sẽ hứng mọi sai sót của lời gọi.
```

vì một số exception là **đồng bộ**. Để phân loại đúng, đặt `try/catch` quanh chỗ khởi tạo request, **và** có chính sách xử lý `failed`/`completed` bên trong handler.

### 7.1. Ví dụ xử lý đồng bộ trước callback

```java
try {
    channel.lock(0L, 4L, false, "task-1", handler);
} catch (OverlappingFileLockException ex) {
    // Cùng JVM đã có lock tương ứng hoặc đang chờ lock chồng lấn.
    // Không giả định callback.failed đã/chắc chắn sẽ được gọi.
} catch (IllegalArgumentException ex) {
    // Lỗi tính phạm vi position/size.
} catch (NonWritableChannelException ex) {
    // Mode mở channel không cho exclusive lock.
}
```

Đây là đoạn minh họa với `channel`, `handler` và các import phù hợp. Cần có thêm chính sách xử lý failure ở tầng gọi, bao gồm xác nhận request có được khởi tạo hay không, không retry vô hạn.

### 7.2. Nếu dùng Future thì xem cause

```java
try {
    FileLock lock = future.get();
    try (lock) {
        // Phần việc được bảo vệ.
    }
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    // Phân loại cause: I/O, closed channel, v.v.
}
```

Đây là đoạn minh họa trong phương thức có `throws InterruptedException` hoặc catch tương ứng. Không so sánh `ExecutionException.getMessage()` như một chuỗi cố định: nguyên nhân mới là dữ liệu kỹ thuật cần xử lý.

### 7.3. Tình huống lỗi do đóng channel

Nếu một operation asynchronous vẫn **pending** và channel bị đóng, theo hợp đồng của các asynchronous channels operation có thể hoàn tất thất bại với **`AsynchronousCloseException`**.

Nhưng nếu channel **đã đóng trước khi khởi tạo** hoặc có lỗi đối số trước đó, lỗi có thể xuất hiện tại thời điểm khác tùy API/provider. Đừng viết test không ổn định bằng cách cố tình đóng channel “đúng 1 ms sau lock” rồi hardcode duy nhất một dạng exception. Khi muốn kiểm tra nhánh `failed` của callback, có thể unit test **gọi trực tiếp callback với lỗi mô phỏng**, đồng thời integration test riêng các lỗi file-system thực tế.

## 8. `tryLock(...)`: thử lấy khóa ngay, không chờ

`AsynchronousFileChannel.tryLock` **không phải** một lời gọi I/O bất đồng bộ. Nó thử lấy lock ngay theo hợp đồng:

```java
FileLock lock = channel.tryLock(0L, 4L, false);
if (lock == null) {
    // Một chương trình khác đang giữ khóa chồng lấn: không lấy được ngay.
} else {
    try (lock) {
        // Phần việc được bảo vệ.
    }
}
```

Đây là đoạn minh họa trong phương thức có xử lý `IOException` và các lỗi đồng bộ có thể xuất hiện.

### 8.1. Trường hợp khác JVM

Khi **một chương trình khác** giữ khóa chồng lấn, `tryLock` có thể trả `null` thay vì chờ. Đây là tình huống tranh chấp lock thật giữa các process. Nhưng hệ thống tệp và OS vẫn có thể phát sinh `IOException` hoặc ràng buộc riêng.

### 8.2. Trường hợp cùng JVM

Nếu JVM **đã giữ lock chồng lấn** hoặc có request chồng lấn pending, `tryLock` thường ném **`OverlappingFileLockException`**, không trả `null`. Lý do: Java ngăn **lock chồng lấn trong cùng tiến trình**, kể cả nếu hai thread/đối tượng channel khác nhau.

### 8.3. Hai ngữ nghĩa không được gộp

| Kết quả | Ý nghĩa |
| --- | --- |
| `FileLock` hợp lệ | Đã lấy được khóa: phải có owner và phải release |
| `null` | Chưa lấy được khóa ngay do một chương trình khác có khóa chồng lấn |
| `OverlappingFileLockException` | Xung đột với lock đã giữ/pending trong cùng JVM |
| `IOException` / `ClosedChannelException` | Lỗi I/O hoặc channel/lifecycle |
| `IllegalArgumentException` | Vùng khóa không hợp lệ |

Đừng viết vòng `while (tryLock(...) == null) { }` không delay: sẽ gây **busy loop**, tiêu thụ CPU và có thể chặn việc khác. Chọn retry có backoff, deadline và cancellation nếu nghiệp vụ cần chờ.

## 9. Chồng lấn vùng khóa và `FileLock.overlaps`

`FileLock.overlaps(candidatePosition,candidateSize)` trả boolean khi vùng được hỏi chồng lấn ít nhất **một byte** với vùng lock đã biểu diễn.

```java
FileLock lock = /* khóa đã lấy thành công */;

boolean inside = lock.overlaps(2L, 1L);
boolean nextTo = lock.overlaps(4L, 1L);
```

Đây là đoạn minh họa với `lock` đang đại diện cho vùng `[0,4)`. Khi đó `inside == true`, `nextTo == false`. Không dựa vào kiểm tra `overlaps` trên object để thay thế hoàn toàn logic cấp phát vùng khóa giữa nhiều thread vì state có thể thay đổi đồng thời.

### 9.1. Hai khóa không chồng lấn có thể cùng tồn tại

Ví dụ trên cùng file:

```text
Future lock A:   [0, 4)       exclusive
Handler lock B:  [4, 8)       exclusive
```

Các khóa không có byte chung nên không bị cấm bởi quy tắc chống overlap trong cùng JVM. Chương trình hoàn chỉnh bên dưới dùng đúng hai vùng này và kiểm thử callback được gọi thành công.

### 9.2. Vùng chồng lấn sẽ bị từ chối trong cùng JVM

Khi khóa A `[0,4)` còn hiệu lực, gọi `channel.tryLock(2L,1L,false)` sẽ ném `OverlappingFileLockException` trong môi trường kiểm thử và theo hợp đồng kiểm soát overlap. Không nhất thiết phải có một process ngoài mới xuất hiện lỗi này.

**Không retry ngay cùng một vùng không thay đổi trạng thái**: nếu thread A còn giữ lock thì thread B trong cùng JVM có thể tiếp tục nhận exception. Cần giao thức nội bộ xác định ai sở hữu vùng nào và khi nào release.

## 10. Vòng đời và quyền sở hữu `FileLock`

`FileLock` bắt đầu hợp lệ khi lấy thành công. Nó giữ hiệu lực cho đến khi:

- Ứng dụng gọi `lock.release()` hoặc `lock.close()`.
- Channel dùng để lấy lock bị đóng.
- JVM kết thúc.
- Hoặc một điều kiện phù hợp khiến lock không còn valid theo hợp đồng môi trường.

Dùng:

```java
try (FileLock lock = channel.lock(0L, 4L, false).get()) {
    // Chỉ thực hiện phần công việc cần khóa trong phạm vi này.
}
```

Đây là đoạn minh họa trong phương thức xử lý `InterruptedException` và `ExecutionException`, đồng thời các lỗi khởi tạo lock. `FileLock` triển khai `AutoCloseable`; kết thúc khối gọi `close()`, vốn gọi `release()`.

### 10.1. Giải phóng lock là việc bắt buộc kể cả khi code lỗi

Nếu phần xử lý trong vùng khóa ném exception và bạn không có `finally`/`try-with-resources`, lock có thể còn được giữ lâu hơn dự kiến. Hậu quả có thể là tiến trình khác tiếp tục chờ hoặc ứng dụng gặp overlap khi yêu cầu vùng đó lần nữa.

Một nguyên tắc an toàn:

1. Yêu cầu lock.
2. Khi thành công, **bàn giao ownership** rõ ràng cho một object/task.
3. Bao phần xử lý bằng `try-with-resources` hoặc `finally` bảo đảm release.
4. Nếu release thất bại, báo lỗi; không mặc định khóa đã được dọn sạch.
5. Không giữ khóa trong suốt thời gian sống của server chỉ vì quên đóng channel.

### 10.2. Đóng channel ảnh hưởng tới lock

`channel.close()` làm những lock lấy qua channel đó mất hiệu lực. Khi một async lock còn pending, close cũng ảnh hưởng tới kết quả hoàn tất.

Đừng chủ động đóng channel từ một callback chỉ để dọn một lock, nếu channel còn phục vụ các tác vụ khác. Ngược lại, khi owner đóng channel trong shutdown, các task cần biết rằng lock I/O của chúng không còn tiếp tục như trước.

### 10.3. Một file, một channel chuyên trách thường dễ kiểm soát hơn

Trên **một số hệ điều hành**, đóng **bất kỳ channel nào** trỏ tới một file có thể làm mất **tất cả lock của JVM** trên file đó, dù lock được lấy qua channel khác. Java khuyến nghị trong một chương trình nên dùng **một channel duy nhất để sở hữu các lock trên một file** nếu có thể.

Đây là lưu ý quan trọng khi ứng dụng có nhiều component mở cùng một file. Việc đóng một channel “không liên quan” có thể tác động tới cơ chế phối hợp khóa trên một số nền tảng.

### 10.4. `acquiredBy()` và `channel()`

`FileLock.acquiredBy()` trả channel đã cấp khóa dưới dạng `Channel`, làm việc được với cả `FileChannel` và `AsynchronousFileChannel`.

`FileLock.channel()` trả `FileChannel` và có thể là **`null` nếu lock đến từ `AsynchronousFileChannel`**. Khi xử lý lock từ async channel, dùng `acquiredBy()` thay vì ép dựa vào `channel()`.

### 10.5. Không dùng `isValid()` như cơ chế chống race

`isValid()` phản ánh trạng thái tại thời điểm gọi. Một thread khác có thể đóng channel ngay sau khi bạn kiểm tra `isValid()==true`. Do đó thao tác I/O vẫn phải xử lý lỗi tại thời điểm thực hiện; kiểm tra hợp lệ trước không thay thế giao thức đồng bộ và ownership.

## 11. Cancellation, timeout, shutdown và tác vụ pending

### 11.1. Timeout của caller

Khi gọi `future.get(5,SECONDS)`:

- Nếu lock hoàn tất trước hạn, bạn nhận `FileLock`.
- Nếu hết hạn, `TimeoutException` chỉ nói caller chưa có kết quả trong thời gian đó.
- Future và native operation **có thể vẫn tiếp tục**.
- Bạn phải quyết định tiếp tục theo dõi, hủy hoặc đóng channel theo ownership.

Nếu dùng callback, có thể đặt deadline bên ngoài, đánh dấu request đã hết hạn và **khi callback `completed` đến muộn phải release lock ngay hoặc chuyển đúng owner**. Không thả mất tham chiếu đến lock đã được cấp.

### 11.2. Hủy Future

`Future.cancel(boolean mayInterruptIfRunning)` có thể làm các thread đợi nhận `CancellationException`, nhưng kết quả đối với underlying asynchronous operation phụ thuộc implementation. Một số trạng thái channel sau cancellation có thể bị ảnh hưởng theo cách phụ thuộc provider.

Không đưa ra cam kết chung rằng `cancel(true)` lập tức giải phóng mọi lock native hoặc mọi callback dừng đúng thời điểm. Thiết kế cleanup/test theo JDK và filesystem thực tế.

### 11.3. Shutdown channel

Khi đóng `AsynchronousFileChannel`:

- Các thao tác async đang outstanding có thể hoàn tất lỗi với `AsynchronousCloseException`.
- Những `FileLock` đã cấp qua channel bị invalid.
- Callback có thể chạy trên thread pool để báo completion; không đặt giả định rằng thread gọi close sẽ tự thực thi toàn bộ callback.
- Các tác vụ nghiệp vụ cần xử lý trạng thái “lock chưa lấy được / lock vừa mất / operation canceled” theo hợp đồng của service.

Nếu ứng dụng cần bảo đảm những tác vụ đã nhận xử lý xong trước khi shutdown, phải có cơ chế **đợi task/worker**, không chỉ gọi `channel.close()`.

### 11.4. Không dùng file lock để thay thế transaction

File lock có thể phối hợp với chương trình khác theo giao thức, nhưng không bảo đảm:

- Mọi write là atomic hoặc sẽ được rollback nếu process crash.
- Buffer được tự động flush ra thiết bị khi release.
- Độc giả có thể thấy file ở cùng một phiên bản bất biến trong mọi OS.
- Các thread trong cùng JVM không thể làm hỏng dữ liệu khi không phối hợp.

Nếu bài toán cần tính bền vững, cân nhắc `channel.force(true/false)` theo hợp đồng, log/checksum và quy trình publish/snapshot. **`force`, file lock và transaction là những cơ chế khác nhau**.

## 12. Ví dụ Java 17+ đầy đủ đã biên dịch và chạy

Chương trình `AsyncRegionLockDemo` được thiết kế để minh họa **cả hai dạng completion thành công** và nhiều nhóm lỗi xác định được **không phụ thuộc may rủi thời điểm cạnh tranh giữa process**:

1. Tạo thư mục và file nhị phân tạm 16 byte.
2. Mở `AsynchronousFileChannel` với READ và WRITE.
3. Yêu cầu exclusive lock `[0,4)` bằng `Future<FileLock>`, chờ tối đa 5 giây.
4. Kiểm tra `isValid/position/size/isShared` và `overlaps` với vùng chồng lấn và vùng kề cạnh.
5. Cố `tryLock` vùng chồng lấn `[2,3)` trong cùng JVM; bắt `OverlappingFileLockException`.
6. Yêu cầu khóa vùng **không chồng lấn** `[4,8)` qua `CompletionHandler<FileLock,String>`. Callback `completed` giải phóng khóa và đánh dấu kết quả.
7. Sau khi release khóa đầu, `tryLock(0,4,false)` lại thành công.
8. Kiểm tra tham số không hợp lệ `position=-1` ném `IllegalArgumentException` ngay lúc gọi.
9. Gọi trực tiếp callback `failed` bằng một `IOException` do test tự tạo để xác minh nhánh lỗi — **đây là unit test mô phỏng callback, không phải lỗi I/O thực tế**.
10. Mở một channel chỉ READ và yêu cầu exclusive lock; nhận `NonWritableChannelException` đồng bộ.
11. Đóng channel/lock và dọn toàn bộ fixture tạm.

**Các dòng output từ khóa thật** được xác minh trên file system mặc định Windows; đường lỗi `failed` được xác minh bằng **đầu vào mô phỏng chủ động**, nhằm không cần can thiệp ACL hoặc chạy một process khác để gây tranh chấp bất định.

Tạo file **`AsyncRegionLockDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.CompletionHandler;
import java.nio.channels.FileLock;
import java.nio.channels.NonWritableChannelException;
import java.nio.channels.OverlappingFileLockException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class AsyncRegionLockDemo {
    private static void check(boolean value, String reason) {
        if (!value) throw new AssertionError(reason);
    }

    private static final class LockHandler
            implements CompletionHandler<FileLock, String> {
        final CountDownLatch done = new CountDownLatch(1);
        final AtomicReference<String> outcome =
                new AtomicReference<>("pending");
        final AtomicReference<Throwable> failure = new AtomicReference<>();

        @Override
        public void completed(FileLock lock, String attachment) {
            try (FileLock owned = lock) {
                check(owned.isValid(), "lock must be valid");
                check(owned.position() == 4L && owned.size() == 4L,
                        "handler region");
                outcome.set("completed:" + attachment);
            } catch (Throwable error) {
                failure.set(error);
                outcome.set("cleanup-failed:" + attachment);
            } finally {
                done.countDown();
            }
        }

        @Override
        public void failed(Throwable error, String attachment) {
            failure.set(error);
            outcome.set("failed:" + attachment + ":"
                    + error.getClass().getSimpleName());
            done.countDown();
        }

        String await() throws InterruptedException {
            check(done.await(5, TimeUnit.SECONDS), "handler timed out");
            return outcome.get();
        }
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("async-region-lock-");
        Path file = directory.resolve("record.bin");
        try {
            Files.write(file, new byte[16], StandardOpenOption.CREATE_NEW);

            try (AsynchronousFileChannel channel =
                    AsynchronousFileChannel.open(
                            file,
                            StandardOpenOption.READ,
                            StandardOpenOption.WRITE)) {
                Future<FileLock> future = channel.lock(0L, 4L, false);
                FileLock first = future.get(5, TimeUnit.SECONDS);

                try (first) {
                    check(first.isValid() && first.position() == 0L
                            && first.size() == 4L && !first.isShared(),
                            "future lock");
                    System.out.println("future lock valid = " + first.isValid());
                    System.out.println("future lock range = " + first.position()
                            + ".." + (first.position() + first.size()));
                    System.out.println("overlaps 2..3 = "
                            + first.overlaps(2L, 1L));
                    System.out.println("overlaps 4..5 = "
                            + first.overlaps(4L, 1L));

                    try {
                        channel.tryLock(2L, 1L, false);
                        throw new AssertionError(
                                "overlapping lock unexpectedly acquired");
                    } catch (OverlappingFileLockException expected) {
                        System.out.println("same-JVM overlap = "
                                + expected.getClass().getSimpleName());
                    }

                    LockHandler handler = new LockHandler();
                    channel.lock(4L, 4L, false, "other-region", handler);
                    String result = handler.await();

                    check(handler.failure.get() == null, "handler error");
                    check(result.equals("completed:other-region"),
                            "handler completion");
                    System.out.println("callback outcome = " + result);
                    check(first.isValid(), "first lock remains valid");
                }

                System.out.println("first valid after release = "
                        + first.isValid());

                try (FileLock reacquired =
                        channel.tryLock(0L, 4L, false)) {
                    check(reacquired != null && reacquired.isValid(),
                            "reacquire after release");
                    System.out.println("tryLock after release = "
                            + reacquired.isValid());
                }

                try {
                    channel.lock(-1L, 1L, false);
                    throw new AssertionError("invalid position accepted");
                } catch (IllegalArgumentException expected) {
                    System.out.println("invalid range = "
                            + expected.getClass().getSimpleName());
                }

                LockHandler simulated = new LockHandler();
                simulated.failed(new IOException("synthetic failure"), "unit-test");
                String simulatedResult = simulated.await();
                check(simulatedResult.equals("failed:unit-test:IOException"),
                        "simulated failure callback");
                System.out.println("simulated failure callback = "
                        + simulatedResult);
            }

            try (AsynchronousFileChannel readOnly =
                    AsynchronousFileChannel.open(
                            file, StandardOpenOption.READ)) {
                try {
                    readOnly.lock(0L, 1L, false);
                    throw new AssertionError(
                            "exclusive lock on READ channel");
                } catch (NonWritableChannelException expected) {
                    System.out.println("exclusive on READ-only = "
                            + expected.getClass().getSimpleName());
                }
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }

        System.out.println("cleanup = done");
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 AsyncRegionLockDemo.java
java AsyncRegionLockDemo
```

**Stdout chính xác đã được kiểm thử:**

```text
future lock valid = true
future lock range = 0..4
overlaps 2..3 = true
overlaps 4..5 = false
same-JVM overlap = OverlappingFileLockException
callback outcome = completed:other-region
first valid after release = false
tryLock after release = true
invalid range = IllegalArgumentException
simulated failure callback = failed:unit-test:IOException
exclusive on READ-only = NonWritableChannelException
cleanup = done
```

### 12.1. Vì sao lock `[0,4)` và `[4,8)` có thể cùng tồn tại?

Hai vùng kề nhau nhưng không có byte chung. Future của vùng thứ nhất hoàn tất thành công; callback của vùng thứ hai cũng được gọi thành công. Đây là lý do nên xác định phạm vi khóa theo offset/size thay vì cứ khóa cả file theo thói quen.

### 12.2. `overlaps` có phải luôn đúng với mọi vị trí?

Với vùng `[0,4)`, câu hỏi `overlaps(2,1)` có byte 2 chung nên trả `true`. Câu hỏi `overlaps(4,1)` chỉ đề cập byte 4, ngoài vùng A, nên trả `false`.

### 12.3. Vì sao `OverlappingFileLockException` đến từ `tryLock`?

Khi còn giữ lock A, chương trình gọi thử lock một vùng nằm bên trong A. Trong cùng JVM, Java không cho phép hai lock chồng lấn. **Đây là exception đồng bộ**, không phải callback `failed`.

Không diễn giải đây là lỗi “một process ngoài đang giữ lock”. Hai tình huống **cùng JVM** và **khác process** có biểu hiện khác nhau.

### 12.4. Vì sao callback dùng `CountDownLatch`?

Callback completion có thể chạy trên thread pool. Thread điều phối chỉ được phép khẳng định đã xong sau khi nhận tín hiệu hoàn tất. `CountDownLatch.await(5,SECONDS)` có timeout, nên test không chờ vô hạn nếu callback không được gọi; `AtomicReference` giúp truyền kết quả an toàn giữa thread.

### 12.5. Vì sao callback đã release `FileLock`?

Sau `completed`, callback là nơi nhận một tài nguyên lock thật. Trong ví dụ này, mục tiêu chỉ là kiểm chứng hoàn tất và giải phóng; vì thế nó release ngay trong `try-with-resources`. Trong ứng dụng production có xử lý cần được khóa, **không release trước khi phần việc được bảo vệ xong**; chuyển ownership chính thức nếu xử lý bởi worker khác.

### 12.6. Vì sao sau `first` release lại lấy được khóa cùng vùng?

Thoát `try(first)` gọi `FileLock.close()`/`release()`. Vì khóa cũ không còn valid, `tryLock(0,4,false)` có thể lấy lại vùng đó nếu không có process khác giữ xung đột. Test cho thấy `first.isValid()==false` và khóa mới hợp lệ.

### 12.7. Thử `failed` có phải lỗi lock thực?

**Không.** Dòng `simulated failure callback` xuất phát từ việc gọi **trực tiếp** `simulated.failed(new IOException("synthetic failure"), "unit-test")` để kiểm chứng code xử lý lỗi. Nó không chứng minh hệ điều hành đã từ chối một async lock operation.

Để test thực sự callback bị gọi do lỗi I/O, cần một integration test có thể điều khiển hoàn cảnh lỗi, timeout, channel lifecycle hoặc process cạnh tranh; những thử nghiệm như vậy thường phụ thuộc provider và nên tách khỏi demo độc lập.

### 12.8. Vì sao `catch(Throwable)` xuất hiện trong callback demo?

Đây là **test harness** thu nhận cả lỗi assertion và lỗi cleanup để `CountDownLatch` luôn được giải phóng, giúp thread điều phối biết callback đã thất bại. Trong code sản xuất, không nên dùng `catch(Throwable)` một cách chung chung để nuốt lỗi nghiêm trọng; nên phân loại ngoại lệ phù hợp, report qua cấu trúc kết quả thread-safe và bảo toàn những lỗi quan trọng.

### 12.9. Test có an toàn với file thật không?

Ví dụ chỉ tạo file tạm 16 byte trong thư mục tạm do chính chương trình tạo. Mọi lock đều được release/đóng qua lifecycle; sau đó file/thư mục tạm được xóa trong `finally`. Không thử khóa/xóa một file của người dùng hoặc can thiệp quyền hệ thống để mô phỏng lỗi.

Trong môi trường file system không hỗ trợ locking, provider khác hoặc có một process bên ngoài truy cập fixture, thao tác có thể thất bại; stdout trên là kết quả thực tế của môi trường đã kiểm thử, không phải lời hứa mọi OS sẽ phản hồi cùng thời điểm.

## 13. Cách thiết kế workflow bảo vệ bản ghi bằng lock

Một mô hình đơn giản cho những bản ghi fixed-size:

```text
request
   |
   v
validate record offset and byte length
   |
   v
acquire AsynchronousFileChannel lock for [position, position+size)
   |
   +-- failed synchronously? --> report parameter/mode/overlap error
   |
   +-- pending asynchronous? --> await Future or CompletionHandler
                                 |
                                 +-- failed --> classify/propagate cause
                                 |
                                 +-- completed(FileLock)
                                      |
                                      v
                                process protected region
                                      |
                                      v
                                release FileLock in finally
                                      |
                                      v
                                publish result to caller
```

Sơ đồ này là **workflow khái niệm**, không phải cách làm mặc định cho mọi hệ thống. Nó chỉ có ích nếu những tiến trình liên quan cùng tôn trọng giao thức khóa đã được định nghĩa.

### 13.1. Tách lock acquisition và I/O thực

Sau khi lấy được lock, chương trình còn phải **đọc/ghi file** và kiểm tra số byte thực sự xử lý. `AsynchronousFileChannel.write(ByteBuffer, position)` cũng trả Future và số byte ghi hoàn tất có thể nhỏ hơn số byte mong muốn theo hợp đồng; không giả định một lời gọi ghi luôn chuyển hết buffer.

Một ví dụ mô hình:

```java
Future<FileLock> pendingLock =
        channel.lock(recordOffset, recordBytes, false);

// Chỉ sau khi lock hoàn tất thành công:
FileLock lock = pendingLock.get();
try (lock) {
    // Đọc/ghi các byte trong phạm vi theo đúng protocol;
    // chú ý completion của từng read/write và nội dung buffer.
}
```

Đây là đoạn minh họa cần biến `channel`, `recordOffset`, `recordBytes` và xử lý exception đầy đủ. Nếu một tác vụ write được khởi tạo rồi bạn **release lock ngay trước khi write completion**, thao tác ghi vẫn có thể còn pending sau khi khóa đã thả. Phải quản lý thứ tự: **đợi I/O hoàn tất rồi mới release** khi ứng dụng cần bảo đảm vùng luôn được bảo vệ trong thời gian ghi.

### 13.2. Khóa không tự làm I/O trở thành tuần tự

Với async channel, nhiều thao tác read/write có thể outstanding; thứ tự hoàn tất không được bảo đảm là thứ tự khởi tạo. Nếu cần cập nhật nhiều bản ghi theo thứ tự, tầng ứng dụng phải điều phối futures, callbacks hoặc sử dụng một queue/serial executor đúng cách.

Một khóa exclusive đối với chương trình ngoài **không tự giải quyết** race giữa các thread trong JVM đang gửi write ở cùng offset. Sử dụng đồng bộ nội bộ nếu các thread có thể cùng truy cập vùng dữ liệu.

### 13.3. Không chia sẻ `ByteBuffer` đang được I/O sử dụng

Khi một I/O async đang dùng một `ByteBuffer`, không sửa hoặc tái sử dụng buffer đó trước khi thao tác hoàn tất. Lock vùng tệp không thay thế quy tắc ownership của buffer. Buffer cần được giữ sống đúng thời gian của operation và không bị truy cập đồng thời sai cách.

## 14. Độ tin cậy, hiệu năng và giới hạn nền tảng

### 14.1. Network filesystem

Một số network filesystem có giới hạn về vùng lock, căn lề trang bộ nhớ hoặc cơ chế phối hợp giữa máy. Đừng mặc định cùng chương trình chạy tốt trên SSD cục bộ sẽ có ngữ nghĩa lock, độ trễ và khả năng chống race giống hệt trên mọi network share.

Khi ứng dụng cần khóa file trên hệ thống phân tán, hãy kiểm chứng filesystem thực tế và cân nhắc một **dịch vụ điều phối/lease** chuyên dụng nếu file locking không đáp ứng đầy đủ hợp đồng của hệ thống.

### 14.2. Thời gian giữ lock

Giữ lock quá lâu tăng tranh chấp, khiến các tiến trình khác bị chậm hoặc timeout. Với thao tác protected ngắn, cố giới hạn scope của lock vào đúng vùng I/O cần thiết và release sớm **sau khi các I/O liên quan đã hoàn tất**.

Nếu callback phải thực hiện xử lý CPU nặng, nên bố trí worker riêng nhưng có trách nhiệm ownership rõ ràng cho `FileLock`. Không truyền lock sang nhiều task không có cơ chế đảm bảo ai release.

### 14.3. Chống deadlock ở cấp ứng dụng

Hai tiến trình có thể giữ vùng khóa A/B rồi lần lượt chờ vùng còn lại. Java không tự sắp xếp các vùng khóa thay bạn. Khi phải lấy nhiều lock:

- Xác định thứ tự lấy khóa nhất quán (ví dụ offset tăng dần).
- Đặt timeout, backoff và chính sách hủy.
- Tránh giữ một lock trong lúc chờ tài nguyên không liên quan quá lâu.
- Release các khóa đã lấy khi nhiệm vụ bị từ chối.
- Nếu xung đột cùng JVM, dùng cơ chế đồng bộ trong process để tránh request overlap sai cách.

### 14.4. Không thay thế ACL hoặc chống dữ liệu độc hại

FileLock là cơ chế phối hợp truy cập, không phải kiểm soát quyền truy cập. Một chương trình có quyền ghi có thể không tuân thủ advisory lock. Đồng thời file có thể bị thay thế/đổi tên giữa các thao tác khác nhau.

Xử lý input không tin cậy cần các biện pháp kiểm soát path, ownership, quyền hệ điều hành, tính toàn vẹn dữ liệu, xác minh kích thước và khả năng phục hồi. Không coi lock thành công đồng nghĩa file an toàn để parse.

## 15. Phân loại lỗi hoàn tất và hành động tương ứng

| Tín hiệu | Điều cần xác minh | Phản ứng phù hợp |
| --- | --- | --- |
| `IllegalArgumentException` | Offset/size âm, phép cộng bị tràn | Sửa validation; không retry nguyên input |
| `NonWritableChannelException` | Exclusive lock nhưng channel thiếu WRITE | Mở đúng mode nếu có quyền; không đổi thành shared tùy tiện |
| `NonReadableChannelException` | Shared lock nhưng thiếu READ | Mở đúng mode nếu có quyền |
| `OverlappingFileLockException` | Trong JVM đã giữ/đợi lock chồng vùng | Điều phối ownership nội bộ; không coi là external lock contention |
| `tryLock(...) == null` | Tiến trình khác giữ lock chồng lấn | Retry/backoff theo deadline hoặc trả trạng thái bận |
| `ExecutionException` từ `get` | Lỗi async nằm trong `getCause()` | Ghi nhận cause và loại thao tác; không giấu nguồn lỗi |
| `CompletionHandler.failed(Throwable,A)` | Operation đã báo kết thúc thất bại | Chuyển lỗi tới owner, bảo đảm không có caller chờ mãi |
| `InterruptedException` | Thread chờ bị interrupt | Khôi phục status hoặc propagate theo policy |
| `TimeoutException` | Caller chưa có kết quả trước deadline | Theo dõi cancellation/pending lock và cleanup |
| `CancellationException` | Future bị hủy | Kiểm soát lifecycle; không giả định native lock luôn hủy tức thì |
| `AsynchronousCloseException` | Channel bị đóng khi operation pending | Xác định shutdown có chủ đích hay lỗi lifecycle |
| `IOException` trong `release` | Không release được như kỳ vọng | Báo lỗi; quản lý trạng thái channel/lock |
| Timeout khi đợi callback latch | Handler chưa được gọi xong | Không báo thành công; kiểm tra executor và operation lifecycle |

**Quy tắc logging:** ghi operation, file identifier an toàn, region position/size, loại lock, request ID và loại lỗi. Không đưa absolute path nhạy cảm hoặc stack trace không lọc trực tiếp ra giao diện công khai. Không dùng chuỗi `getMessage()` phụ thuộc OS để phân loại lỗi.

## 16. Những lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Gọi `lock` rồi coi khóa đã được lấy ngay | I/O vẫn pending | Dùng Future.get hoặc completed callback |
| Trộn lỗi sync và async vào một catch | Có lỗi bị bỏ sót | Catch tại lúc khởi tạo và xử lý Future/handler |
| Cho rằng `failed` hứng mọi lỗi | Argument/mode/overlap có thể throw ngay | Xử lý synchronous exceptions riêng |
| Nhầm `tryLock` là async vì nằm trên async channel | Logic chờ/callback sai | Nhớ `tryLock` thử ngay và trả `FileLock/null` |
| Nhầm `tryLock()==null` với overlap trong cùng JVM | Retry sai bản chất | Phân biệt external null và OverlappingFileLockException |
| Khóa cả file khi chỉ sửa 4 byte | Tăng tranh chấp | Khóa vùng cụ thể, đúng offset/size |
| Coi `size=0` là vùng rỗng | Khóa lớn ngoài dự kiến | Hiểu size=0 khóa từ position đến EOF |
| Dùng `String.length()` làm byte offset | Sai vị trí với Unicode | Tính byte trong encoding/protocol thực |
| Coi `lock.size()` bằng kích thước file | Sai phép tính dữ liệu | Dùng `channel.size()` để hỏi size |
| Dùng shared=true và giả định chắc chắn shared | Một số provider chuyển sang exclusive | Kiểm tra `lock.isShared()` |
| Dùng file lock làm mutex trong JVM | Không phù hợp vì lock trên danh nghĩa JVM | Dùng Lock/synchronized/queue nội bộ |
| Bỏ quên release khi callback lỗi | Giữ khóa, gây chặn tiến trình khác | Try-with-resources/finally theo owner |
| Timeout Future rồi quên request pending | Khóa có thể được cấp sau đó mà không ai giải phóng | Có cancellation/lifecycle/cleanup rõ ràng |
| Release lock trước khi write async hoàn tất | Vùng không còn được bảo vệ trong lúc ghi | Đợi I/O completion trước release |
| Nghĩ `close` chỉ ảnh hưởng một lock | Channel close có thể làm invalid các lock liên quan | Phân định owner, tránh đóng channel dùng chung |
| Dùng nhiều channel/file không kiểm soát | Platform có thể release nhiều khóa khi đóng một channel | Một channel lock-owner/file khi khả thi |
| Nghĩ lock là mandatory trên mọi hệ điều hành | Advisory lock có thể bị chương trình khác bỏ qua | Thiết kế protocol hợp tác, không thay thế ACL |
| Dựa vào thứ tự các callback để sắp xếp write | Completion có thể đến không đúng thứ tự khởi tạo | Điều phối thứ tự ở tầng ứng dụng |
| Chặn callback pool lâu bằng tác vụ nặng | Giảm throughput, tăng latency | Callback ngắn, worker pool có backpressure |
| Dùng `FileLock.channel()` và ép sang async channel | Có thể nhận null đối với async lock | Dùng `acquiredBy()` |
| Unit test callback bằng lỗi mô phỏng rồi báo đã test lỗi native | Gây kết luận sai về provider | Ghi rõ unit vs integration |
| Đoạn code demo catch(Throwable) rồi im lặng | Có thể che lỗi nghiêm trọng | Chỉ dùng trong test harness có report; production phân loại lỗi |
| Không xử lý close/cancel race | Trạng thái pending/valid không ổn định | Có state machine và ownership rõ |
| Thử khóa file người dùng để test | Có thể gây gián đoạn ứng dụng khác | Tạo fixture riêng trong temp directory |

## 17. Bài tập có đáp án

### Bài 1 — Khóa một vùng bốn byte

Muốn khóa độc quyền byte offset 8, 9, 10, 11 bằng async channel, truyền giá trị gì?

**Đáp án:** `channel.lock(8L,4L,false)`. Vùng là `[8,12)`. Không dùng `size=12` vì đó sẽ khóa tới offset 20.

### Bài 2 — Hai vùng kề nhau

Đã có exclusive lock `[0,4)`, có thể lấy thêm exclusive lock `[4,8)` trong cùng JVM không?

**Đáp án:** Theo quy tắc overlap, có thể vì **không có byte chung**. Vẫn cần provider hỗ trợ và xử lý I/O/lifecycle.

### Bài 3 — Khóa chồng vùng trong cùng JVM

Đã giữ `[0,4)`, gọi `tryLock(2L,1L,false)` trả `null` hay ném exception?

**Đáp án:** Ném `OverlappingFileLockException` trong cùng JVM; `null` là trường hợp `tryLock` không lấy được ngay vì chương trình khác giữ lock chồng lấn.

### Bài 4 — Lỗi completion và lỗi khởi tạo

`channel.lock(-1L,1L,false,attachment,handler)` có bảo đảm gọi `handler.failed` không?

**Đáp án:** Không. Lỗi phạm vi có thể ném **`IllegalArgumentException` ngay tại chỗ gọi**. Phải xử lý synchronous exceptions và async completion ở hai tầng.

### Bài 5 — Future bị timeout

`future.get(1,SECONDS)` ném `TimeoutException`. Có thể bỏ Future rồi kết luận chưa ai giữ lock không?

**Đáp án:** Không. Operation có thể vẫn pending và sau đó được cấp lock. Cần theo dõi lifecycle, có chính sách cancellation/cleanup, tránh khóa bị giữ không ai sở hữu.

### Bài 6 — Shared mode

Channel chỉ mở `READ`, có thể xin shared lock không? Nếu muốn exclusive thì sao?

**Đáp án:** Shared lock cần READ và có thể yêu cầu; exclusive lock cần WRITE, nên channel chỉ READ sẽ gặp `NonWritableChannelException`. Provider có thể cấp exclusive thực tế cho yêu cầu shared nếu shared không được hỗ trợ; xem `isShared()`.

### Bài 7 — Callback đã nhận lock

`completed(FileLock lock, ...)` nhận kết quả. Code chỉ in log rồi thoát mà không release. Có vấn đề gì?

**Đáp án:** Có thể giữ khóa quá lâu, cản các process khác. Callback hoặc owner nhận chuyển giao lock phải release bằng `try-with-resources`/`finally`.

### Bài 8 — Hai thread trong một JVM

Một thread giữ khóa file `[0,4)`, thread thứ hai muốn khóa cùng vùng rồi sửa. Có nên dùng file lock như mutex để điều phối chúng không?

**Đáp án:** Không. Lock file được giữ trên danh nghĩa JVM; Java ngăn overlap và ném exception, không tự cung cấp lock chờ theo thread như `ReentrantLock`. Dùng đồng bộ nội bộ cho thread, file lock khi cần phối hợp process.

### Bài 9 — `size=0`

`channel.lock(100L,0L,false)` có phải không khóa byte nào không?

**Đáp án:** Không. `size=0` nghĩa khóa từ offset 100 tới cuối file, kể cả khi file sau đó thay đổi kích thước.

### Bài 10 — Bảo vệ một write bất đồng bộ

Sau khi lấy khóa, code gọi `channel.write(buffer,position)` rồi release ngay mà không đợi completion. Vì sao sai?

**Đáp án:** Operation write có thể vẫn đang chạy khi lock đã thả. Nếu giao thức yêu cầu bảo vệ toàn bộ quá trình ghi, phải đợi write completion/đảm bảo buffer đúng vòng đời rồi mới release.

### Bài 11 — Tiến trình khác không tuân thủ lock

Một chương trình khác cố tình ghi file dù lock advisory đang được giữ. FileLock của Java có bảo đảm ngăn nó không?

**Đáp án:** Không phải trên mọi hệ điều hành. File locking có thể advisory. Các chương trình cần phối hợp theo giao thức, không dùng lock thay permission/security.

### Bài 12 — `FileLock.acquiredBy`

Một FileLock đến từ `AsynchronousFileChannel`, dùng `lock.channel()` để lấy lại channel và ép sang async channel có đúng không?

**Đáp án:** Không. `channel()` có thể trả null đối với khóa do async channel cấp. Sử dụng `lock.acquiredBy()` khi cần biết channel sở hữu.

### Bài 13 — Vì sao test không ép lỗi native?

Chương trình bài học gọi trực tiếp `handler.failed(new IOException(...),"unit-test")`. Có thể báo đã kiểm chứng provider sẽ luôn gọi failed với IOException đó không?

**Đáp án:** Không. Đây là **unit test nhánh callback**; muốn chứng minh lỗi native cần integration test được kiểm soát trên provider/môi trường thực.

### Bài 14 — Chờ Future và interrupt

Nếu thread đang `future.get()` bị interrupt, nên xử lý ra sao?

**Đáp án:** Theo contract, có thể propagate `InterruptedException` hoặc khôi phục cờ bằng `Thread.currentThread().interrupt()` rồi dừng; đồng thời quản lý **pending lock operation** theo ownership, không tự coi interrupt của waiter đã cancel I/O.

### Bài 15 — Đóng channel khi pending

Một task xin khóa nhưng chưa hoàn tất, owner gọi `channel.close()`. Task nên kết luận gì?

**Đáp án:** Operation có thể kết thúc thất bại với `AsynchronousCloseException`, hoặc phải phân biệt các race khác theo lúc bắt đầu/hoàn tất. Không báo đã lấy lock; kiểm tra callback/Future và dọn tài nguyên đã cấp.

### Bài 16 — Có cần ghi nhớ chỗ release khi đa thread?

Một callback nhận `FileLock` rồi đưa nó cho worker khác làm việc. Ai release?

**Đáp án:** Phải có một owner rõ ràng. Sau khi chuyển ownership thành công, worker giữ lock cho tới khi phần việc được bảo vệ hoàn tất rồi release; nếu việc chuyển giao thất bại, callback phải release. Không cho cả callback và worker tự release tùy tiện mà không có hợp đồng, và không để quên lock.

## 18. Checklist trước khi dùng trong production

- [ ] Đã xác định thực sự cần **phối hợp liên tiến trình** bằng file lock, không nhầm với đồng bộ thread.
- [ ] Mở `AsynchronousFileChannel` với READ/WRITE phù hợp loại khóa.
- [ ] Tính `position`/`size` theo byte, kiểm tra không âm và không tràn phạm vi.
- [ ] Hiểu `size==0` là từ position đến EOF; `lock()` là exclusive toàn file.
- [ ] Phân biệt shared/exclusive và kiểm tra `lock.isShared()` khi cần hành vi thực tế.
- [ ] Biết vùng khóa có thể vượt EOF; không dùng `FileLock.size()` thay kích thước file.
- [ ] Dùng `Future.get` hoặc `CompletionHandler.completed` để biết khóa **thực sự** được cấp.
- [ ] Catch lỗi đồng bộ ở lời gọi lock và lỗi async qua `ExecutionException.getCause()`/`failed()`.
- [ ] Phân biệt `OverlappingFileLockException` cùng JVM với `tryLock()==null` do process khác giữ lock.
- [ ] Có deadline/backoff rõ nếu đợi lock; không busy spin.
- [ ] Khi Future timeout/cancel, còn chính sách quản lý pending operation, late completion và cleanup.
- [ ] Mọi `FileLock` được cấp đều có owner, và được release bằng `try-with-resources`/`finally`.
- [ ] Nếu protected region có read/write async, đợi completion của I/O cần bảo vệ trước khi thả khóa.
- [ ] Không mặc định file lock bảo đảm atomic write, durability, rollback hoặc mandatory enforcement.
- [ ] Callback ngắn, thread-safe và có cơ chế báo lỗi lại cho owner.
- [ ] Không giả định thứ tự callback là thứ tự khởi tạo các operation.
- [ ] Không chia sẻ mutable `ByteBuffer` khi operation còn outstanding.
- [ ] Quản lý vòng đời channel: close có thể làm invalid mọi khóa và làm fail pending operations.
- [ ] Cân nhắc khuyến nghị dùng **một channel sở hữu lock cho một file** vì hạn chế OS.
- [ ] Test sync errors, callback success/failure, release, overlap, shared mode và provider integration theo môi trường.
- [ ] Không ép lỗi/native lock trên tệp thật của người dùng; dùng fixture temp và process kiểm thử có kiểm soát.
- [ ] Phân biệt APIs Java 7 với cú pháp `try(resourceReference)` Java 9 và ví dụ chạy `--release 17`.

## 19. Nguồn API chính thức và kết luận

Các nguồn Java SE chính thức để tra cứu hợp đồng:

- [AsynchronousFileChannel — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): mở channel, lock/tryLock, Future, CompletionHandler, xử lý close và các điều kiện lỗi.
- [FileLock — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileLock.html): vùng khóa, shared/exclusive, validity, release và sự phụ thuộc của nền tảng.
- [CompletionHandler — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): completed/failed và kiểu attachment.
- [OverlappingFileLockException — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/OverlappingFileLockException.html): xung đột khóa chồng lấn trong JVM.

**Tóm lại:** Với `AsynchronousFileChannel`, yêu cầu khóa vùng file có thể được khởi tạo bằng `lock(position,size,shared)` nhận `Future<FileLock>`, hoặc bằng overload với `CompletionHandler<FileLock,A>`. **Có hai tầng lỗi phải quản lý**: lỗi đồng bộ ngay khi gọi API (tham số, mode, overlap) và lỗi xảy ra khi I/O bất đồng bộ hoàn tất (Future thất bại hoặc callback `failed`). Khi khóa được cấp, `FileLock` là **tài nguyên phải release đúng thời điểm**, đặc biệt khi công việc được bảo vệ có I/O async của chính nó.

Không sử dụng file lock để thay mutex trong JVM, không coi mọi file lock là mandatory trên mọi OS, và không để các timeout/cancellation khiến lock được cấp muộn mà không có owner. Chọn vùng byte chính xác, xử lý nguyên nhân lỗi, xác định ownership, đóng channel có trách nhiệm và kiểm thử trên filesystem thực tế là nền tảng để triển khai chức năng khóa vùng tệp an toàn trong Java hiện đại.