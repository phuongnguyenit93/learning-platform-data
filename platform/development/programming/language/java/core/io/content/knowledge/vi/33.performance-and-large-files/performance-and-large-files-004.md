# So sánh stream có bộ đệm, Files.copy và FileChannel khi xử lý tệp lớn

## 1. Vấn đề cần giải quyết

Sao chép một tệp có vẻ đơn giản: đọc byte từ nguồn rồi ghi byte vào đích. Tuy nhiên, với tệp hàng trăm MB, nhiều GB hoặc một luồng dữ liệu hoạt động liên tục, lựa chọn API ảnh hưởng đến **độ phức tạp code, lượng bộ nhớ Java cần cấp phát, số lần gọi I/O, khả năng tận dụng tối ưu hóa hệ điều hành, tính đúng đắn khi có lỗi và cách kiểm thử**.

Trong Java 17+, ba nhóm cách tiếp cận thường gặp:

1. **Stream có bộ đệm:** `BufferedInputStream` + `BufferedOutputStream`, đọc/ghi theo khối bytes.
2. **API cấp cao:** `Files.copy(...)`, yêu cầu Java/provider sao chép tệp hoặc stream theo chính sách options.
3. **NIO channel:** `FileChannel`, với `read`/`write` qua `ByteBuffer`, hoặc `transferTo`/`transferFrom` để yêu cầu chuyển bytes trực tiếp giữa các channel.

Điểm quan trọng nhất:

> **Không có một API luôn nhanh nhất cho mọi môi trường.** `Files.copy` thường là lựa chọn đầu tiên cho copy file đơn giản; buffered stream phù hợp khi cần xử lý byte stream/biến đổi dữ liệu; `FileChannel` hữu ích khi cần offset, chuyển từng vùng, tối ưu I/O theo trường hợp và kiểm soát tiến độ. Hiệu năng thực tế cần được đo trên tệp, thiết bị, OS, provider và workload cụ thể.

Bài này tập trung vào **copy dữ liệu nhị phân đúng nguyên trạng**. Nếu mục tiêu là chuyển đổi charset hoặc xử lý từng dòng văn bản, dùng `Reader`/`Writer` và thiết kế encoding riêng; không biến binary bytes thành String để sao chép.

### 1.1. Luồng dữ liệu tổng quát

```text
Cách A — buffered streams:
Disk/FileSystem → InputStream → [buffer byte] → mã ứng dụng
                                → [buffer byte] → OutputStream → Disk/FileSystem

Cách B — Files.copy:
Path nguồn ───── Files.copy(source, target, options) ─────→ Path đích
                   provider có quyền chọn cơ chế triển khai

Cách C — FileChannel:
FileChannel nguồn → transferTo / transferFrom → Channel đích
       hoặc
FileChannel nguồn → ByteBuffer → FileChannel đích
```

Các sơ đồ nói về **lớp API** chứ không cam kết bao nhiêu bản copy RAM, syscall hay DMA xảy ra dưới nền. Ngay cả cơ chế được gọi là “zero-copy” vẫn chịu điều kiện OS, filesystem, provider, thiết bị và loại channel đích.

## 2. Bảng so sánh nhanh

| Tiêu chí | BufferedInputStream/BufferedOutputStream | `Files.copy` | `FileChannel` |
|---|---|---|---|
| Mức trừu tượng | Đọc/ghi byte stream | Copy file/path hoặc một đầu stream ở mức cao | Truy cập channel byte với position, size, transfer |
| Mức code cần viết | Vòng `read/write` và xử lý EOF | Thường chỉ một lời gọi | Vòng lặp transfer hoặc đọc/ghi ByteBuffer |
| Bộ nhớ ứng dụng | Mảng tạm/buffer kích thước xác định | Implementation quyết định; không yêu cầu caller chứa cả file | Một `ByteBuffer` tái sử dụng, hoặc transfer với bộ đệm do provider/OS chọn |
| Kiểm soát offset | Phải skip/position qua API nguồn thích hợp | Không có tham số offset cho `Files.copy(Path,Path)` | Rõ ràng qua `position` và positional `read/write`/`transferTo` |
| Copy một file sang file | Được, nhưng nhiều code hơn | **Mặc định nên cân nhắc trước** | Được, hữu ích khi cần kiểm soát chi tiết |
| Copy một đoạn file | Có thể nhưng phải tự giới hạn | Không phải mục tiêu của overload Path→Path | Thuận tiện dùng `transferTo(start,count,...)` |
| Native transfer/zero-copy | Không có bảo đảm loại bỏ copy qua buffer user | Tùy provider/implementation | `transferTo` có thể dùng cơ chế tối ưu OS, **không bảo đảm** |
| Thuộc tính tệp | Tự xử lý metadata | Có `COPY_ATTRIBUTES` khi hỗ trợ | Không tự copy metadata chỉ vì chuyển content |
| File rất lớn | Xử lý theo khối, không cần giữ toàn file | Được thiết kế cho copy file thông thường | `size` và offset dùng `long`; vòng lặp xử lý partial transfer |
| Xử lý lỗi/cleanup | Tự kiểm soát hoàn toàn | Ngắn gọn nhưng vẫn có partial target khi thất bại | Cần kiểm soát số byte chuyển và dừng khi không tiến độ |
| Độ bền sau mất điện | Không tự bảo đảm | Không tự bảo đảm | Không tự bảo đảm; có `FileChannel.force` với phạm vi riêng |

**Chọn API theo yêu cầu trước, tối ưu sau.** Bài toán sao chép một ảnh 3 MB khác với gửi từng phần một log vài trăm GB tới socket, hoặc nhân bản hàng nghìn file nhỏ kèm metadata.

## 3. Buffered stream: đọc và ghi theo khối

### 3.1. Cách hoạt động

`InputStream.read()` từng byte có thể làm chương trình mất nhiều lượt chuyển giữa các tầng I/O. `BufferedInputStream` gom dữ liệu đọc vào buffer nội bộ; `BufferedOutputStream` gom những lần write nhỏ trước khi chuyển cho stream bên dưới.

Một copy theo khối không cần đọc toàn file:

```java
try (InputStream in = new BufferedInputStream(Files.newInputStream(source));
     OutputStream out = new BufferedOutputStream(
             Files.newOutputStream(
                     target,
                     StandardOpenOption.CREATE_NEW,
                     StandardOpenOption.WRITE))) {

    byte[] chunk = new byte[64 * 1024];
    int n;

    while ((n = in.read(chunk)) != -1) {
        out.write(chunk, 0, n);
    }
}
```

Đây là **đoạn mã trong method có xử lý `IOException`**, giả định `source` và `target` là `Path` đã xác định, với import `java.io.*`, `java.nio.file.Files` và `StandardOpenOption`. Nó minh họa luồng control chính, còn ví dụ hoàn chỉnh ở phần 7.

Ý nghĩa:

- `chunk` là buffer do caller cấp phát một lần, kích thước 64 KiB.
- `read(chunk)` trả số byte **thực tế** đọc được, không nhất thiết bằng 64 KiB.
- `-1` biểu thị EOF; khi đọc được `n` byte, chỉ có `chunk[0..n-1]` hợp lệ cho lượt đó.
- `out.write(chunk,0,n)` ghi đúng số byte đã đọc; bỏ tham số `n` có thể làm dữ liệu cuối bị lặp từ lượt trước.
- `try-with-resources` đóng các stream kể cả khi lỗi; đóng buffered output sẽ flush dữ liệu còn nằm trong bộ đệm Java trước khi đóng đầu ra bên dưới.
- `CREATE_NEW` tránh tình cờ ghi đè đường dẫn đích đã tồn tại; nếu đích đã có, lời gọi mở sẽ báo lỗi theo contract.

### 3.2. Buffered stream và mảng truyền vào có thể đều là buffer

Trong ví dụ có **ba mức** liên quan bộ nhớ:

1. Buffer nội bộ của `BufferedInputStream`.
2. Mảng `byte[] chunk` 64 KiB ứng dụng tái sử dụng.
3. Buffer nội bộ của `BufferedOutputStream`.

Vì ứng dụng đã đọc và ghi theo khối 64 KiB, việc bọc thêm hai `Buffered*Stream` đôi khi **không mang lại lợi ích rõ rệt** so với `Files.newInputStream`/`newOutputStream` với cùng mảng lớn. Buffered wrapper đặc biệt hữu ích nếu phần xử lý phía trên gọi `read/write` nhiều lần với khối nhỏ.

Không kết luận “càng nhiều lớp buffer càng nhanh”. Bộ nhớ dư, sao chép thêm qua các tầng và flush pattern có thể làm khác hiệu năng. **Benchmark cả phương án có/không có wrapper** nếu tối ưu throughput là mục tiêu.

### 3.3. Chọn kích thước buffer

Những giá trị như 8 KiB, 32 KiB, 64 KiB, 256 KiB hoặc 1 MiB chỉ là **ứng viên benchmark**, không phải đáp án chung. Buffer quá nhỏ thường tăng số lời gọi I/O; buffer quá lớn có thể tăng footprint, pressure lên cache/bộ nhớ và số byte phải cấp phát mỗi worker.

Với vòng lặp copy, tài nguyên nhớ do ứng dụng giữ là **O(B)** với B là kích thước buffer, trong khi dung lượng file có thể lớn hơn RAM. Nếu 100 worker đồng thời mỗi worker giữ một mảng 1 MiB, riêng mảng tạm đã khoảng 100 MiB chưa kể buffers, queue và runtime overhead.

Lưu ý `InputStream.read(byte[])` trả dữ liệu từng phần theo trạng thái nguồn. Không được giả định một lần đọc tương ứng một file block, một bản ghi hay một TCP message.

### 3.4. `flush()`, `close()` và độ bền

`out.flush()` yêu cầu đẩy các byte đang đệm xuống lớp output bên dưới. `close()` của buffered output sẽ xử lý flush rồi đóng stream bên dưới. Nhưng:

- `flush()` **không đồng nghĩa** dữ liệu đã fsync tới thiết bị.
- `close()` **không tự bảo đảm** file an toàn sau mất nguồn trên mọi filesystem.
- Nếu cần durability mạnh, phải thiết kế thêm sync/force và thường cả cơ chế công bố file đích an toàn.
- Nếu xảy ra `IOException` giữa chừng, file đích có thể đã có **một phần** nội dung, không được coi là bản copy hoàn chỉnh.

Dữ liệu có thể đã đọc đúng 100% nhưng ghi ra đích bị lỗi hoặc đĩa đầy; code vẫn phải để exception đi ra ngoài và xử lý trạng thái đích.

## 4. `Files.copy`: cách trực tiếp cho thao tác copy file

### 4.1. Overload Path → Path

Ví dụ đơn giản:

```java
Path source = Path.of("data.bin");
Path target = Path.of("backup.bin");

Files.copy(source, target);
```

Đây là đoạn minh họa trong method xử lý `IOException` với `Path`/`Files` đã import. Theo contract, nếu `target` đã tồn tại thì mặc định có thể ném `FileAlreadyExistsException`. Nếu chủ động cho phép thay thế:

```java
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
```

`REPLACE_EXISTING` thay đổi chính sách khi target đã có; **không** biến toàn bộ copy thành thao tác atomic. Nếu cần giữ metadata khi được hỗ trợ:

```java
Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES);
```

Các snippet nằm trong method có xử lý `IOException`, dùng các loại `java.nio.file.*`. `COPY_ATTRIBUTES` yêu cầu copy thuộc tính file, nhưng tập attributes được copy và độ chính xác của chúng phụ thuộc file system/provider. Đừng suy ra mọi ACL, owner, extended attributes và timestamp đều được bảo toàn tuyệt đối trên mọi OS.

**Ưu điểm lớn:** code ngắn, dễ đọc, ít cơ hội mắc lỗi vòng lặp/EOF và cho provider quyền tối ưu con đường sao chép. Nếu chỉ cần copy một file bình thường, đây thường là API nên thử đầu tiên.

### 4.2. Không suy luận implementation của `Files.copy`

Việc gọi `Files.copy(Path,Path)` **không cam kết** Java luôn dùng:

- Một `BufferedInputStream` cụ thể;
- Một buffer có size cố định;
- Một syscall `sendfile` / `copy_file_range` cụ thể;
- Zero-copy trong mọi trường hợp;
- Một chiến lược tối ưu giống nhau giữa các OS/JDK/provider.

`Files.copy` xác định **hành vi cấp API**, còn cách thực hiện tùy implementation, kiểu file, quyền truy cập, hệ thống tệp và môi trường. Các nhận xét hiệu năng phải gắn phiên bản JDK và platform đã đo.

### 4.3. `Files.copy` không phải giao dịch nguyên tử

Tài liệu Java không bảo đảm thao tác copy tổng thể diễn ra nguyên tử. Khi lỗi I/O xảy ra, file đích có thể tồn tại với dữ liệu không đầy đủ. Không dùng trực tiếp đường dẫn đích quan trọng rồi giả định người đọc không bao giờ thấy phiên bản đang được tạo.

Một cách tổ chức thường dùng khi cập nhật một file quan trọng:

```text
source
  │
  └── Files.copy(...) → staging file trong cùng directory với target
                              │
                              ├── kiểm tra length/checksum/điều kiện
                              ├── sync file staging nếu yêu cầu durability
                              └── publish qua rename nguyên tử nếu hỗ trợ
                                           │
                                           └── sync directory theo platform nếu cần crash durability
```

Cần phân biệt: `Files.copy` không tự thực hiện tất cả các bước này. `Files.move(..., ATOMIC_MOVE)` chỉ có contract riêng cho atomic move khi hỗ trợ; nó **không tự đồng nghĩa** directory entry đã bền sau mất điện. Việc thay target đã tồn tại với `ATOMIC_MOVE` còn phụ thuộc implementation và không nên giả định có behavior giống nhau mọi provider.

### 4.4. Overload liên quan InputStream và OutputStream

`Files` còn có hai overload tiện lợi:

```java
long n1 = Files.copy(inputStream, target,
        StandardCopyOption.REPLACE_EXISTING);

long n2 = Files.copy(source, outputStream);
```

Đoạn trên là **minh họa** với `inputStream`/`outputStream` đã mở, `source`/`target` là các `Path` và caller xử lý `IOException`. Cả hai overload này trả `long` là số byte đã copy.

Điểm khác với Path→Path:

- `Files.copy(InputStream, Path, ...)` lấy nguồn là stream và tạo/ghi target.
- `Files.copy(Path, OutputStream)` đọc file rồi gửi byte tới output stream.
- Hai overload **không tự đóng stream do caller truyền vào**; người sở hữu phải quản lý `close`/`flush`.
- `Files.copy(Path,Path,...)` trả về **`Path` đích**, không phải byte count. Nếu cần số byte, dùng `Files.size` trước/sau hoặc copy qua API trả số byte theo contract.
- Cùng tên `copy` nhưng options và semantics về attributes có khác theo overload; đọc chữ ký mình thực sự gọi.

Không cố truyền `COPY_ATTRIBUTES` cho overload `InputStream→Path` như thể nó hỗ trợ sao chép metadata từ một stream vốn không có đường dẫn hay thuộc tính file tương đương.

## 5. `FileChannel`: xử lý bằng `ByteBuffer`

`FileChannel` thuộc Java NIO, cung cấp file position, size, random access và một số thao tác transfer. Nó thích hợp khi cần sao chép từng đoạn hoặc tích hợp với các pipeline channel.

### 5.1. Copy thủ công bằng `read`/`write`

Một vòng copy channel có thể trông như:

```java
try (FileChannel in = FileChannel.open(source, StandardOpenOption.READ);
     FileChannel out = FileChannel.open(target,
             StandardOpenOption.CREATE_NEW,
             StandardOpenOption.WRITE)) {

    ByteBuffer buffer = ByteBuffer.allocateDirect(64 * 1024);

    while (in.read(buffer) != -1) {
        buffer.flip();
        while (buffer.hasRemaining()) {
            out.write(buffer);
        }
        buffer.clear();
    }
}
```

Đây là **đoạn minh họa trong method xử lý `IOException`**, với `source`/`target` hợp lệ và imports `FileChannel`, `ByteBuffer`, `StandardOpenOption`. Để bảo vệ trước provider bất thường mà một lượt `read`/`write` báo không tiến độ kéo dài, production nên theo dõi số byte và chính sách retry/break thay vì vòng bận vô hạn.

**Quy tắc ByteBuffer bắt buộc:**

1. Ban đầu `position=0`, `limit=capacity`, sẵn sàng nhận byte.
2. `in.read(buffer)` đưa bytes vào vùng từ position tới limit; position tăng theo lượng đọc.
3. `buffer.flip()` đặt limit theo vị trí đã ghi và position về 0 để xuất byte.
4. `out.write(buffer)` có thể ghi **ít hơn** số byte còn lại; dùng `while(buffer.hasRemaining())`.
5. `buffer.clear()` chuẩn bị buffer nhận đợt mới; **không xóa byte vật lý** trong buffer, chỉ đặt lại cursor.

Nếu bỏ `flip()`, có thể ghi byte cũ hoặc không đúng vùng. Nếu quên `clear()`, buffer sẽ hết không gian ghi. Nếu chỉ gọi `out.write(buffer)` một lần và mặc định hết `remaining()`, file đích có thể mất một phần dữ liệu.

### 5.2. `allocateDirect` có luôn tốt hơn `allocate`?

Không. `ByteBuffer.allocateDirect(n)` dùng một vùng direct memory, có thể thuận tiện cho native channel I/O; `ByteBuffer.allocate(n)` dùng heap buffer thông thường. Sự khác biệt hiệu năng phụ thuộc kích thước transfer, JDK, GC, CPU, OS và memory pressure.

Direct buffers có chi phí cấp phát và lifecycle riêng, không phải “miễn phí RAM”. **Cấp phát một lần rồi tái sử dụng** trong vòng copy thay vì `allocateDirect` ở mỗi lượt. Với job rất nhỏ, heap buffer có thể đơn giản và đủ nhanh.

### 5.3. Vòng lặp phải xử lý partial writes

`FileChannel.write(ByteBuffer)` trả số byte thực tế đã ghi. Kể cả file channel đồng bộ, contract vẫn không hứa mọi `remaining()` sẽ hết trong một lời gọi. Vì vậy:

```java
while (buffer.hasRemaining()) {
    int n = targetChannel.write(buffer);
    if (n <= 0) {
        throw new IOException("Target did not make progress");
    }
}
```

Đoạn minh họa giả định `targetChannel` đang mở ghi và `buffer` chứa byte để gửi. Nếu môi trường thực yêu cầu chấp nhận `n=0` một cách tạm thời, thiết kế retry/backoff/timeout riêng; không spin vô hạn.

## 6. `FileChannel.transferTo` và `transferFrom`

### 6.1. `transferTo(position,count,target)`

Ví dụ:

```java
long copied = sourceChannel.transferTo(
        offset, requestedBytes, targetChannel);
```

Đây là snippet với `sourceChannel` kiểu `FileChannel` đã mở đọc và `targetChannel` kiểu `WritableByteChannel` hợp lệ. Ý nghĩa:

- `offset` là vị trí **byte trong file nguồn**, kiểu `long`.
- `requestedBytes` là số byte **tối đa muốn chuyển** trong lời gọi, kiểu `long`.
- Kết quả `copied` là số byte **thực tế đã chuyển** trong lần đó, có thể nhỏ hơn số yêu cầu.
- File position của **source FileChannel** không bị thay đổi bởi `transferTo` vì offset được truyền tường minh.
- Nếu target channel có position, bytes được ghi từ vị trí hiện tại của **target**, và target position tăng tương ứng.

**Không được kết luận** một lần `transferTo(0, source.size(), target)` luôn chuyển toàn bộ file. Provider/OS có thể giới hạn kích thước một lượt, target có thể không nhận hết hoặc có điều kiện khiến phương thức trả 0.

### 6.2. Loop cho file lớn

Mẫu phổ biến:

```java
long size = sourceChannel.size();
long position = 0L;

while (position < size) {
    long n = sourceChannel.transferTo(
            position, size - position, targetChannel);

    if (n <= 0) {
        // Không được quay lại vòng lặp y nguyên mãi mãi.
        throw new IOException(
                "No progress at file offset " + position);
    }

    position += n;
}
```

Đoạn này là **minh họa trong method**; `sourceChannel` và `targetChannel` đã mở. Nó phát hiện và báo lỗi khi transfer không tiến được; tùy use case, có thể chuyển sang phương thức read/write dự phòng cho phần còn lại.

### 6.3. Vì sao có thể nhận 0 hoặc ít bytes?

Một số tình huống:

- Requested region đến cuối file; nếu tính offset sai, không còn bytes để chuyển.
- Target channel không thể nhận thêm byte ngay (đặc biệt non-blocking target).
- Cơ chế native transfer bị giới hạn theo OS hoặc provider.
- File nguồn bị thay đổi kích thước trong khi copy.
- Bất kỳ giới hạn implementation nào khiến số bytes trong một lời gọi nhỏ hơn số yêu cầu.

Cách xử lý không thể chỉ `while(n==0) continue` mãi mãi. Có thể dùng fallback `FileChannel.read(ByteBuffer,offset)` rồi `target.write(ByteBuffer)` với kiểm soát tiến độ, hoặc fail rõ để caller xử lý.

### 6.4. `transferFrom` chuyển theo chiều ngược lại

```java
long n = targetFileChannel.transferFrom(
        readableSourceChannel, fileOffset, maxBytes);
```

Đoạn trên giả định `targetFileChannel` là FileChannel mở ghi và `readableSourceChannel` là `ReadableByteChannel`. `transferFrom` chuyển bytes từ **nguồn** vào FileChannel đích từ offset được chỉ định.

Lưu ý quan hệ position khác với `transferTo`:

- `transferFrom` truyền **position của file đích** tường minh; position hiện tại của FileChannel đích không thay đổi.
- Nếu source channel có position, vị trí nguồn có thể tiến khi byte được đọc.
- Kết quả thực tế cũng có thể nhỏ hơn `maxBytes`; vẫn phải lập kế hoạch loop và xử lý tiến độ.
- Một nguồn socket/pipe khác file có semantics readiness và EOF riêng; không thể áp mọi giả định file-to-file sang non-blocking network.

### 6.5. “Zero-copy” là khả năng, không phải cam kết API

Trên những tổ hợp OS/file/channel cụ thể, `transferTo` có thể dùng đường truyền native giúp giảm số lần sao chép dữ liệu qua user space hoặc số lần syscall. Nhưng Java API **không cam kết rằng mỗi `transferTo` sẽ luôn là zero-copy**.

Đừng suy diễn:

- Chắc chắn không có dữ liệu nào được copy ở RAM/OS.
- Chắc chắn không sử dụng page cache.
- Chắc chắn không có CPU overhead hoặc context switches.
- Chắc chắn nhanh hơn buffered streams với file nhỏ.
- Chắc chắn có cùng semantics trên Windows, Linux, macOS và network filesystem.

Việc `FileChannel` cho phép provider triển khai tối ưu là **lợi thế tiềm năng**. Để khẳng định hiệu quả thật, phải đo với tổ hợp triển khai thực.

## 7. Ví dụ Java 17+ chạy được: ba cách copy và kiểm tra byte

Ví dụ độc lập sau:

- Tạo một thư mục riêng và file nguồn có **131.075 byte** (cố ý không chia hết cho 64 KiB).
- Copy bằng buffered streams.
- Copy bằng `Files.copy(Path,Path)`.
- Copy bằng `FileChannel.transferTo`, với fallback sang `read/write(ByteBuffer)` nếu transfer không tiến độ.
- So sánh byte với `Files.mismatch` (Java 12+, nên có trong Java 17+).
- Dọn file của chính ví dụ, không chạm file của người dùng.

**Tệp:** `CopyStrategiesDemo.java`

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.stream.Stream;

public class CopyStrategiesDemo {

    private static long copyBuffered(Path source, Path target)
            throws IOException {

        long bytesCopied = 0;

        try (InputStream in = new BufferedInputStream(
                    Files.newInputStream(source));
             OutputStream out = new BufferedOutputStream(
                    Files.newOutputStream(
                            target,
                            StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE))) {

            byte[] chunk = new byte[64 * 1024];
            int n;

            while ((n = in.read(chunk)) != -1) {
                out.write(chunk, 0, n);
                bytesCopied += n;
            }
        }

        return bytesCopied;
    }

    private static long copyWithChannel(Path source, Path target)
            throws IOException {

        try (FileChannel in = FileChannel.open(
                    source, StandardOpenOption.READ);
             FileChannel out = FileChannel.open(
                    target,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {

            long size = in.size();
            long position = 0L;
            ByteBuffer fallback = ByteBuffer.allocateDirect(64 * 1024);

            while (position < size) {
                long moved = in.transferTo(
                        position, size - position, out);

                if (moved > 0) {
                    position += moved;
                    continue;
                }

                // Native transfer không tiến được:
                // đọc đúng vùng còn lại bằng positional read.
                fallback.clear();
                fallback.limit((int) Math.min(
                        (long) fallback.capacity(),
                        size - position));

                int read = in.read(fallback, position);
                if (read <= 0) {
                    throw new IOException(
                            "Cannot make progress at " + position);
                }

                fallback.flip();

                while (fallback.hasRemaining()) {
                    int written = out.write(fallback);

                    if (written <= 0) {
                        throw new IOException("Target stalled");
                    }
                }

                position += read;
            }

            return position;
        }
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory(
                "copy-strategies-");

        try {
            Path source = directory.resolve("source.bin");

            byte[] data = new byte[131_075];
            for (int i = 0; i < data.length; i++) {
                data[i] = (byte) (i * 31 + 7);
            }

            Files.write(source, data);

            Path buffered = directory.resolve("buffered.bin");
            Path filesCopy = directory.resolve("files-copy.bin");
            Path channel = directory.resolve("channel.bin");

            System.out.println(
                    "source bytes: " + Files.size(source));

            System.out.println(
                    "buffered bytes: "
                    + copyBuffered(source, buffered));

            Files.copy(source, filesCopy);

            System.out.println(
                    "Files.copy equal: "
                    + (Files.mismatch(source, filesCopy) == -1));

            System.out.println(
                    "channel bytes: "
                    + copyWithChannel(source, channel));

            boolean same =
                    Files.mismatch(source, buffered) == -1
                    && Files.mismatch(source, filesCopy) == -1
                    && Files.mismatch(source, channel) == -1;

            System.out.println("all equal: " + same);

        } finally {
            // Chỉ dọn các file được tạo trong thư mục của demo.
            try (Stream<Path> entries = Files.list(directory)) {
                for (Path entry : entries.toList()) {
                    Files.deleteIfExists(entry);
                }
            }
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac CopyStrategiesDemo.java
java CopyStrategiesDemo
```

**Stdout dự kiến khi filesystem thông thường hoạt động đúng:**

```text
source bytes: 131075
buffered bytes: 131075
Files.copy equal: true
channel bytes: 131075
all equal: true
```

### 7.1. Giải thích lựa chọn trong demo

- Dùng dữ liệu byte **định trước** thay cho Random để stdout/so sánh tái lập được.
- `131_075` không chia hết cho `65_536`; lượt đọc cuối chỉ có 3 byte sau hai khối đầy, giúp kiểm tra code không ghi dư byte.
- `CREATE_NEW` yêu cầu file đích chưa tồn tại và ngăn ghi đè không chủ ý.
- `Files.copy` được gọi không có option vì đích là đường dẫn mới.
- `Files.mismatch(a,b)` trả `-1` khi toàn bộ bytes và chiều dài bằng nhau; có thể dùng để kiểm tra file copy **tại thời điểm đọc**, không phải hash hay chứng nhận dữ liệu sau mất điện.
- Hàm channel khởi tạo `position=0`, chuyển tới khi đủ `size`. Nếu `transferTo` không tiến, nó dùng positional `read` vào một buffer direct tái sử dụng rồi ghi đủ bytes sang FileChannel đích.
- Vì không có thread nào thay đổi source/target trong demo, cách đếm `position` và file size là ổn định. **Trong hệ thống có writer đồng thời**, cần cơ chế bảo đảm snapshot/độ ổn định riêng.
- `finally` chỉ dọn file trong **thư mục tạm do demo tạo**. Nếu một bước trước đó lỗi, cleanup cũng có thể ném IOException; trong ứng dụng thật cần chính sách log/giữ file lỗi tùy nhu cầu khôi phục.

### 7.2. Tại sao không in số millisecond “benchmark”?

Tốc độ copy bị ảnh hưởng bởi page cache, trạng thái filesystem và tải máy. In `System.nanoTime()` một lần rồi gắn nhãn “API X nhanh nhất” là kết luận không có ý nghĩa phổ quát. Ví dụ cố tình chỉ xác nhận **tính đúng đắn** bằng byte counts và `Files.mismatch`. Phần đo hiệu năng được giải thích riêng bên dưới.

### 7.3. Vì sao fallback channel không gọi `read`/`write` đồng thời với một transfer đang chạy?

`FileChannel.transferTo` đồng bộ đối với lời gọi này: nó đã trả về số byte chuyển được (hoặc 0) trước khi fallback bắt đầu. Trong demo không có transfer bất đồng bộ pending giữ buffer; fallback đọc lại đúng `position` còn lại rồi gửi tới output hiện tại.

**Điều kiện tiên quyết:** cả source và target không bị thread khác thay đổi, và output channel được mở mới với position 0. Nếu bạn chuyển `transferTo` đến socket non-blocking, phải thêm cơ chế readiness/backpressure riêng, không sao chép nguyên vòng lặp fallback file-to-file này.

## 8. Tệp lớn hơn 2 GiB: dùng `long`, xử lý từng phần

Các file rất lớn không thể được biểu diễn bằng một `byte[]` có độ dài vượt giới hạn array JVM, và `ByteBuffer` có `capacity`/`position` kiểu `int`. Nhưng `FileChannel.size()`, positional offsets và các tham số `transferTo`/`transferFrom` dùng `long`.

Vì vậy:

- Không chuyển `channel.size()` về `int` khi tệp có thể lớn hơn 2 GiB.
- Không dùng `Files.readAllBytes` chỉ để copy một file hàng chục GB: có thể thất bại do giới hạn array hoặc cạn heap.
- Dùng buffer kích thước hữu hạn và vòng lặp, để bộ nhớ không tăng theo kích thước file.
- Tính offset bằng `long`, kiểm tra overflow khi cộng `position + n`.
- Tránh cast `(int)(size - position)` nếu phần còn lại có thể lớn hơn `Integer.MAX_VALUE`. Chỉ cast sau khi giới hạn bằng `Math.min(remaining, (long) buffer.capacity())`.
- Với `transferTo`, đừng đưa ra giả định “count kiểu long thì OS chuyển hàng TB trong một syscall”; vẫn phải lặp theo giá trị thực trả về.

### 8.1. Chia copy thành các đoạn có kích thước logic

Ví dụ muốn giới hạn mỗi lần yêu cầu transfer ở 64 MiB:

```java
long offset = 0L;
long size = sourceChannel.size();
long maxChunk = 64L * 1024 * 1024;

while (offset < size) {
    long requested = Math.min(maxChunk, size - offset);
    long n = sourceChannel.transferTo(
            offset, requested, targetChannel);

    if (n <= 0) {
        throw new IOException("No transfer progress at " + offset);
    }

    offset += n;
}
```

Đây là **snippet minh họa trong method**, với hai channel đã mở. 64 MiB là một kích thước tham khảo, không phải giới hạn bắt buộc của Java. Nếu source thay đổi concurrent, `size` có thể không còn phản ánh cuối file thật, nên cần quyết định copy **snapshot tại đầu** hay theo dõi thay đổi theo giao thức riêng.

### 8.2. Copy một vùng của file

`FileChannel` tiện khi chỉ cần byte [start,start+length):

```java
long start = 1_048_576L;
long length = 4_194_304L;
long copied = 0L;

while (copied < length) {
    long n = sourceChannel.transferTo(
            start + copied,
            length - copied,
            targetChannel);

    if (n <= 0) {
        throw new IOException("Could not copy requested region");
    }

    copied += n;
}
```

Đây là snippet trong method, giả định vùng byte yêu cầu tồn tại hoàn toàn trong source và target đang ở đúng position. Nếu file nhỏ hơn `start+length`, không coi copy thiếu byte là thành công; kiểm tra `size`/source integrity phù hợp và xử lý EOF.

### 8.3. Với copy nhiều file, metadata và directory tree cũng quan trọng

`Files.copy` một Path đến một Path **không tự đệ quy copy toàn bộ cây thư mục có nội dung** nếu source là directory; khi copy directory, hành vi chỉ tạo/copy directory entry hoặc thuộc tính theo contract, còn entries bên trong cần được xử lý riêng. Copy một cây cần thuật toán duyệt, xử lý symlink/cycle, file permissions, metadata và lỗi từng tệp.

Cũng đừng nhầm `Files.copy` một lần là giải pháp incremental backup: nó không tính diff, version, deduplication, checksum lịch sử hoặc transaction toàn cây.

## 9. Hiệu năng: đọc số đo đúng cách

### 9.1. Throughput và latency đo các khía cạnh khác nhau

- **Throughput:** số byte copy thành công trên mỗi giây, ví dụ MiB/s.
- **Latency:** thời gian từ lúc bắt đầu copy tới lúc API hoàn tất cho một file.
- **Tail latency:** p95/p99 khi có nhiều file/jobs, quan trọng với hệ thống phục vụ request.
- **Memory footprint:** heap/direct memory/temporary buffers trên mỗi operation.
- **CPU utilization:** CPU bị tiêu thụ khi copy.
- **Syscall count/context switching:** đôi khi làm rõ ích lợi của buffered/transfer.
- **Durability time:** nếu yêu cầu `force`/sync, phải đo cả phần đó, không chỉ thời gian bytes vào cache.

Một API có throughput cao với một file 20 GB có thể lại kém đối với hàng triệu file 1 KiB do overhead mở/đóng, metadata lookup và scheduling. Cũng có thể Files.copy đã tận dụng tối ưu hóa của provider khiến vòng loop tự viết không nhanh hơn.

### 9.2. Bộ nhớ và tần suất gọi I/O

Một vòng `read(chunk)` với `chunk.length = B` cần khoảng `ceil(fileSize/B)` lần đọc trong trường hợp mỗi read đầy đủ, **nhưng thực tế có thể nhiều hơn** do partial reads. Số lần ghi cũng phụ thuộc việc ghi partial và buffering.

Ví dụ tính toán minh họa: một file 1 GiB với khối 64 KiB tương ứng 16.384 khối nếu tất cả khối trừ cuối đều đầy. Đây chỉ là **ước lượng số chunk**, không phải số syscall chính xác của OS, vì lớp buffering, provider và native transfer có thể hoạt động khác.

Điều quan trọng là **không gọi `read()`/`write()` từng byte** khi copy file lớn nếu không có yêu cầu đặc biệt; lập chiến lược buffer phù hợp và đo.

### 9.3. Page cache khiến benchmark dễ sai

Trong một hệ thống tệp điển hình, OS có page cache và read-ahead. Nếu chạy:

```text
Lượt 1: buffered copy
Lượt 2: Files.copy
Lượt 3: FileChannel
```

thì lượt 2/3 có thể được hưởng dữ liệu nguồn đã nằm trong cache, dẫn đến kết luận thiên lệch rằng “lượt sau nhanh hơn”.

Các yếu tố gây nhiễu:

- Warm/cold cache của hệ điều hành và JVM.
- Antivirus/indexing/background I/O.
- SSD/HDD/NVMe, network mount, filesystem/compression/deduplication.
- Khả năng copy nội bộ cùng filesystem hoặc giữa hai thiết bị.
- Direct buffer allocation và GC.
- Độ dài/lượng file, kích thước buffer, số worker đồng thời.
- Sync/durability option và tốc độ thực của thiết bị.
- File hệ thống thưa (sparse file), symlink và thuộc tính file.

### 9.4. Quy trình benchmark có ý nghĩa hơn

1. **Xác định workload:** file nhỏ, file 100 MB, 5 GB; một file hay nhiều file; copy cùng volume hay khác volume; sequential hay chunked.
2. **Định nghĩa cùng semantics:** cả ba phương án đều copy bytes giống hệt, xử lý overwrite/attributes/flush giống nhau nếu những điều đó thuộc yêu cầu.
3. **Warm-up:** chạy nhiều lượt cho JIT và hệ thống ổn định; đừng chọn lần đầu làm kết luận cuối.
4. **Đổi thứ tự chạy:** luân phiên các chiến lược để giảm hiệu ứng cache.
5. **Lặp nhiều mẫu:** lấy median và phân bố, ghi môi trường JDK/OS/filesystem/media.
6. **Theo dõi correctness:** size, `Files.mismatch` hoặc checksum trong test thích hợp. Không dùng throughput của file copy bị thiếu byte.
7. **Tách thời gian copy và verify:** việc đọc lại toàn file để `mismatch` có chi phí; báo hai thước đo riêng.
8. **Đo memory/CPU khi cần:** dùng profiler, JFR hoặc các công cụ OS thích hợp, không chỉ thời gian nanoTime.
9. **Kiểm tra failure scenarios:** disk full, permission errors, target tồn tại, source bị xóa/thay đổi, network filesystem bị ngắt.
10. **Báo kết luận có phạm vi:** “trong máy thử và loại file này”, không nói API nào nhanh nhất cho mọi JVM.

`System.nanoTime()` phù hợp đo khoảng thời gian đơn lẻ trong một test tự kiểm soát; với microbenchmark cực ngắn, dùng framework như JMH và cẩn thận tác động của OS I/O vì JMH không loại bỏ mọi yếu tố cache/device.

### 9.5. Mẫu đo đơn giản, không tuyên bố benchmark chuẩn

```java
long startNanos = System.nanoTime();

Files.copy(source, destination);

long elapsedNanos = System.nanoTime() - startNanos;
long byteCount = Files.size(destination);

double seconds = elapsedNanos / 1_000_000_000.0;
double mibPerSecond = seconds > 0
        ? (byteCount / 1_048_576.0) / seconds
        : Double.POSITIVE_INFINITY;
```

Đây là **snippet minh họa** trong method xử lý `IOException`; `source`/`destination` là Path, destination chưa tồn tại. Nó không có stdout cố định, không bao gồm file verify và không phản ánh chắc chắn lưu bền. Không lấy một con số MiB/s từ đoạn này để áp cho môi trường khác.

## 10. Correctness: làm thế nào xác minh bản sao?

Một file copy “thành công” cần định nghĩa rõ điều gì được bảo toàn:

| Yêu cầu | Cách kiểm tra |
|---|---|
| Nội dung bytes chính xác | `Files.mismatch(source,target)==-1` khi cả hai không bị thay trong lúc kiểm tra |
| Kích thước bằng nhau | `Files.size(source)==Files.size(target)`, cần thiết nhưng không đủ |
| Thời gian sửa đổi, quyền, owner | Đọc `BasicFileAttributes` hoặc view phù hợp; copy metadata riêng |
| Không ghi đè dữ liệu có sẵn | `CREATE_NEW` hoặc default `Files.copy` khi target đã tồn tại |
| Chấp nhận overwrite có chủ đích | `REPLACE_EXISTING` cho `Files.copy` hoặc open options tương ứng |
| Crash durability | Thiết kế `force`/sync, staging và publish theo OS/filesystem |
| Copy từ một phiên bản nhất quán | Snapshot, lock/protocol, version/checksum hoặc cơ chế lưu trữ tương đương |
| Bảo mật đường dẫn | Validate/canonicalize theo trust boundary, xử lý symlink và quyền |

`Files.mismatch` trả **vị trí byte đầu tiên khác** hoặc `-1` nếu không có khác biệt; nếu file sizes khác nhau, trả vị trí đầu tiên mà file ngắn không còn byte. Nó không phải thuật toán hash bảo mật và không phát hiện/giải quyết mọi race khi nguồn/đích có thể bị sửa đồng thời.

### 10.1. Vì sao kích thước bằng nhau chưa đủ?

Hai file đều 1 MB có thể khác toàn bộ bytes. Nếu chỉ kiểm tra `Files.size`, bug copy sai thứ tự, ghi dữ liệu cũ hoặc thay đổi offset sẽ bị bỏ qua. `mismatch` hoặc checksum phù hợp giúp xác minh nội dung trong bài test.

Ngược lại, nếu tệp có metadata quan trọng, bytes giống nhau vẫn chưa bảo đảm file đích có đúng quyền, attributes hay link semantics.

## 11. Tệp đang bị thay đổi trong lúc copy

Cả ba cách không tự tạo một **snapshot có tính giao dịch** của file nguồn đang được writer khác chỉnh sửa.

Giả sử:

```text
T0: source.bin = version A
T1: copy đọc nửa đầu version A
T2: writer khác sửa nửa sau thành version B
T3: copy đọc nửa sau version B
T4: target có thể là hỗn hợp A/B
```

Ngay cả khi `Files.copy` thành công, dữ liệu đích chưa chắc tương ứng một thời điểm logic duy nhất. Khi tính nhất quán quan trọng:

- Dừng writer hoặc dùng cơ chế lock/protocol giữa các bên **có hợp tác**.
- Dùng snapshots của filesystem/storage nếu có và được xác nhận.
- Thiết kế copy từ **file bất biến** theo phiên bản; ghi bản mới riêng và publish pointer sau.
- Ghi checksum/version khi phát hành và validate sau khi copy; kiểm tra lại source nếu policy yêu cầu.
- Đừng cho rằng `FileLock` mang lại transaction hoàn chỉnh giữa mọi process hoặc trên mọi filesystem; semantics tùy OS/provider.

### 11.1. Một byte-stream copy không biết cấu trúc file nghiệp vụ

Với database file, WAL, log nhiều file hay cấu trúc được cập nhật nhiều bước, chỉ copy các bytes trong lúc dịch vụ đang chạy có thể tạo snapshot logic sai. Nên dùng API backup/snapshot chính thức của hệ thống lưu trữ đó hoặc quy trình application-consistent backup, thay vì tự copy file đang được thay đổi mà không hiểu cấu trúc.

## 12. Overwrite, symlink và metadata

### 12.1. Copy file mới khác cập nhật file đang tồn tại

`Files.copy(source,target)` mặc định không thay target hiện hữu. `Files.copy(source,target,REPLACE_EXISTING)` yêu cầu thay target nếu được phép. Nhưng thay đích **không phải atomic publish**; người đọc có thể nhìn thấy trạng thái không phù hợp khi copy đang diễn ra hoặc gặp lỗi.

Khi copy theo buffered stream/channel, các option:

- `CREATE_NEW`: tạo mới và fail nếu file đã tồn tại.
- `CREATE`: tạo nếu chưa tồn tại, không tự ngụ ý truncate nếu thiếu option liên quan.
- `TRUNCATE_EXISTING`: cắt ngắn nếu mở ghi và file tồn tại theo contract.
- `APPEND`: thêm vào cuối, **không phải copy ghi đè từ đầu**.

Dùng chính sách thích hợp; không kết hợp `APPEND` với công việc copy nguyên trạng vào một file trống một cách vô ý.

### 12.2. Symlink và đường dẫn

Với `Files.copy(Path,Path)`, nếu source là symbolic link, mặc định thường **theo link** và copy nội dung target được tham chiếu; `LinkOption.NOFOLLOW_LINKS` có thể dùng khi muốn copy chính link theo contract của provider.

```java
Files.copy(
        source,
        target,
        LinkOption.NOFOLLOW_LINKS);
```

Đây là snippet minh họa trong method xử lý `IOException`; hành vi tạo/copy symlink và quyền hỗ trợ phụ thuộc filesystem/provider. Nếu đường dẫn được người dùng cung cấp và chương trình có quyền cao, kiểm tra path traversal, symlink races và thư mục cho phép trước khi thao tác. Một check `Files.exists` rồi write riêng **không phải** rào chắn race tuyệt đối; dùng atomic create options và chính sách OS phù hợp khi cần.

### 12.3. Copy attributes và permissions

`StandardCopyOption.COPY_ATTRIBUTES` áp dụng trong overload `Files.copy(Path,Path)`; tập thuộc tính được bảo toàn tùy provider và filesystem. Trên một số nguồn/đích, quyền, owner, ACL, extended attributes, timestamp precision hoặc creation time có thể khác.

Khi làm backup, metadata đôi khi quan trọng ngang nội dung; cần liệt kê attrs bắt buộc và kiểm tra sau copy. Đừng chấm hiệu năng của cách chỉ copy content rồi so với cách cũng sao chép permissions/metadata mà không ghi rõ sự khác biệt.

## 13. Độ bền file sau khi copy

**“Method trả về thành công” không tự có nghĩa “file sống sót qua mất điện”.** File system và OS có thể buffer dữ liệu. Các API:

- `BufferedOutputStream.flush()`: đẩy bytes ở buffer Java xuống stream bên dưới; không mặc định fsync.
- `Files.copy`: không phải lệnh sync durability có contract chung cho mọi thiết bị.
- `FileChannel.force(false)`: yêu cầu flush thay đổi content theo phạm vi API.
- `FileChannel.force(true)`: yêu cầu flush content và metadata theo phạm vi API; bảo đảm mạnh hơn trên thiết bị lưu trữ cục bộ theo điều kiện contract.
- `Files.move(...,ATOMIC_MOVE)`: nếu hỗ trợ thì atomicity của thao tác move, **khác** durability sau crash.
- Đồng bộ parent directory entry sau rename: phụ thuộc OS/provider và có thể cần API nền tảng ngoài Java SE portable.

Nếu bản copy sẽ thay một file cấu hình quan trọng, thiết kế thường có:

```text
tạo file tạm trong cùng thư mục
        │
        ▼
copy toàn bộ bytes vào staging
        │
        ▼
kiểm tra bản sao (size/checksum/schema)
        │
        ▼
force/sync staging khi yêu cầu durable
        │
        ▼
rename nguyên tử nếu provider hỗ trợ
        │
        ▼
sync directory theo contract nền tảng nếu cần crash consistency
        │
        ▼
chỉ xác nhận commit ở mức đã thực sự bảo đảm
```

Không tự suy diễn rằng `FileChannel.force(true)` trên staging trước rename cũng đồng bộ **directory entry sau rename**. Với dữ liệu quan trọng, cần chính sách backup/recovery và kiểm thử failure mode trên storage thực.

## 14. Xử lý lỗi và cleanup khi copy thất bại

Một số tình huống phải tính:

| Tình huống | Rủi ro | Hướng xử lý |
|---|---|---|
| Source không tồn tại | `NoSuchFileException` hoặc IOException | Không tạo bản sao trống giả thành công |
| Target đã tồn tại | `FileAlreadyExistsException` theo chính sách mặc định/CREATE_NEW | Chọn rõ overwrite hay không |
| Disk full/quota | Bản đích có thể đã được ghi một phần | Dọn staging/target theo policy, không publish |
| Permission denied | Không mở/ghi được file | Kiểm tra quyền, trả lỗi rõ |
| File nguồn đổi kích thước | Copy thiếu hoặc dữ liệu pha nhiều phiên bản | Lock/snapshot/phiên bản bất biến |
| `transferTo` trả 0 khi còn bytes | Loop không tiến, nguy cơ spin | Fallback hoặc fail |
| `write(ByteBuffer)` ghi một phần | Truncation dữ liệu | Lặp tới hết `remaining()` |
| Source/target là cùng file | Có thể tự ghi đè/cắt ngắn nguồn | Validate identity; tránh copy lên chính nguồn |
| I/O giữa các volumes/FS | Tốc độ và semantics khác | Benchmark/tính đúng trên cặp đích thực |
| Process bị dừng đột ngột | File chưa copy hết | Copy staging, trạng thái phục hồi và cleanup |

Nếu sao chép tới file tạm mà thất bại, không đổi tên file tạm thành target. Cách cleanup tùy nghiệp vụ: có thể xóa staging ngay, hoặc giữ bản sao dở dang để resume có kiểm tra checksum/chunk map. Tuyệt đối không đánh dấu file đích “completed” chỉ vì tồn tại.

### 14.1. Thời gian chờ và hủy copy

Với file lớn hoặc copy qua network filesystem, một operation có thể mất nhiều thời gian. Vòng buffered stream/channel tự viết có thể kiểm tra cờ dừng giữa các chunk, nhưng cần hiểu những lệnh I/O đang block có thể chưa trả ngay khi cờ đổi.

`Files.copy` cấp cao không cung cấp trực tiếp callback tiến độ cho mỗi block ở overload Path→Path. Nếu cần progress UI hoặc cancellation từng khối, việc tự quản lý chunk/byte count ở stream/channel có thể phù hợp hơn.

Không ghi progress “100%” trước khi flush/close/verify theo định nghĩa hoàn tất của sản phẩm. Với các yêu cầu durability, trạng thái “byte đã chuyển” và “commit đã bền” là hai mốc khác nhau.

### 14.2. Log và metrics

Đối với job copy lớn, nên ghi:

- Kích thước nguồn đã xác minh, tên job hoặc ID an toàn.
- Số byte đã chuyển, thời gian, throughput đo được với nhãn môi trường.
- API/chiến lược thực tế được dùng và fallback đã xảy ra hay chưa.
- Phân loại lỗi: permissions, disk full, source truncated, target stalled, checksum mismatch.
- Trạng thái: STARTED / COPYING / VERIFYING / COMMITTED / FAILED.

Không log nguyên nội dung tệp nhạy cảm hoặc đường dẫn chứa token/secret nếu không cần. Tại thời điểm báo COMMITTED, các điều kiện “đã copy / đã verify / đã sync / đã publish” phải được ghi nhận chính xác.

## 15. Nên dùng API nào trong từng tình huống?

### Trường hợp A: copy một file thông thường

```java
Files.copy(source, target);
```

Ưu tiên vì ngắn, rõ mục đích, dễ xử lý options. Chỉ chuyển sang tự viết loop khi cần behavior mà API cấp cao không cung cấp hoặc benchmark đáng tin chứng minh có ích.

### Trường hợp B: chuyển InputStream nhận từ API khác thành file

```java
long bytes = Files.copy(
        inputStream,
        target,
        StandardCopyOption.REPLACE_EXISTING);
```

Khi stream thuộc caller, caller phải đóng nó theo ownership contract. Với nguồn không tin cậy, **giới hạn bytes khi nhận** bằng một wrapper/loop có hard cap; một lời gọi copy thẳng không tự đặt quota do ứng dụng mong muốn.

### Trường hợp C: cần xử lý từng chunk (checksum/progress/cancel)

Dùng stream loop hoặc `FileChannel.read/write` để đo bytes, cập nhật checksum và kiểm tra cờ stop tại những điểm rõ ràng. Khi muốn thay đổi nội dung, buffered stream cho từng chunk có thể dễ hiểu hơn. `FileChannel` có lợi nếu cũng cần random access hoặc positional I/O.

### Trường hợp D: cần copy một đoạn của file rất lớn

Dùng `FileChannel.transferTo(start,length,target)` với loop xử lý partial transfer; hoặc positional reads/writes qua ByteBuffer nếu native transfer không phù hợp. Đảm bảo offsets là `long` và không vượt file size theo dữ liệu đã kiểm chứng.

### Trường hợp E: tối ưu truyền bytes từ file tới socket

`FileChannel.transferTo` có thể tận dụng đường tối ưu từ file tới một `WritableByteChannel` phù hợp, nhưng với socket non-blocking phải quản lý readiness/backpressure và kết quả transfer partial hoặc 0. Không áp đoạn loop file-to-file có giả định write luôn tiến lên socket theo cách thiếu kiểm soát.

### Trường hợp F: backup với metadata và crash consistency

Không có một lời gọi nào trong ba cách tự mang toàn bộ semantics backup. Cần kiểm kê metadata, snapshot logic, staging/verify, durability và atomic publish theo filesystem, cùng policy recovery.

## 16. Lỗi phổ biến

1. **`Files.readAllBytes` toàn bộ file nhiều GB chỉ để copy.** Có thể vượt giới hạn mảng/heap.
2. **Đọc/ghi từng byte bằng I/O không buffer** trong vòng lớn. Tăng overhead; nên dùng chunk.
3. **Nghĩ `read(chunk)` luôn lấp đầy mảng.** Phải dùng `n` được trả về.
4. **Ghi `out.write(chunk)` ở lượt cuối dù chỉ đọc ít byte.** Có thể ghi lại dữ liệu cũ.
5. **Quên `close`/`try-with-resources`.** Rò rỉ file descriptor và bỏ sót flush.
6. **Cho rằng `flush` tương đương fsync.** Không có bảo đảm durability như vậy.
7. **Gọi `Files.copy` lên target đã tồn tại mà không đặt overwrite policy.** Có thể ném `FileAlreadyExistsException`.
8. **Dùng `REPLACE_EXISTING` rồi nghĩ copy atomic.** Replace option không biến copy thành transaction.
9. **Cho rằng `COPY_ATTRIBUTES` giữ mọi ACL/metadata trên mọi FS.** Provider có giới hạn.
10. **Cho rằng `Files.copy` luôn zero-copy.** Implementation cụ thể quyết định.
11. **Cho rằng `FileChannel.transferTo` luôn zero-copy.** Java API không cam kết.
12. **Chỉ gọi `transferTo` một lần và nghĩ đã copy hết.** Có thể partial transfer.
13. **Khi `transferTo` trả 0, cứ loop ngay vô hạn.** Cần xử lý progress/fallback/fail.
14. **Nhầm offset file với `ByteBuffer.position`.** Hai vị trí khác nhau; transferTo có positional source offset.
15. **Dùng `int` cho size/offset file nhiều GB.** Tràn số và copy sai vùng.
16. **Cast kích thước còn lại sang `int` trước khi giới hạn.** Có thể thành số âm/sai.
17. **Quên `flip()` sau channel read.** Buffer chưa sẵn sàng cho write.
18. **Quên `clear()` sau đã consume bytes.** Vòng tiếp thiếu chỗ nhận.
19. **Cho rằng một `FileChannel.write` ghi hết `remaining()`.** Có thể partial write.
20. **Cấp phát direct ByteBuffer mới mỗi chunk.** Tăng chi phí/tài nguyên không cần thiết.
21. **Benchmark một lần theo thứ tự cố định.** Dễ bị cache và tải nền bóp méo.
22. **So cách copy bytes thuần với cách vừa copy attributes/force rồi kết luận nhanh-chậm.** Khác semantics nên so sánh không công bằng.
23. **Đo bao gồm verify ở cách này nhưng không ở cách khác.** Kết quả throughput thiên lệch.
24. **Nghĩ file size bằng nhau là bytes giống nhau.** Cần `Files.mismatch` hoặc kiểm tra nội dung thích hợp.
25. **Nghĩ `Files.mismatch==-1` chứng minh durability.** Nó chỉ so sánh bytes ở thời điểm đọc.
26. **Copy file đang bị sửa đồng thời và mặc định có snapshot nhất quán.** Có thể trộn phiên bản.
27. **Copy trực tiếp vào file quan trọng rồi không xử lý trạng thái lỗi một phần.** Nên staging/verify/publish theo policy.
28. **Quên xử lý symbolic links** trong tree copy hoặc input path không tin cậy.
29. **Nghĩ `Files.copy` copy đệ quy cả cây directory.** Nó không tự sao chép mọi entry con.
30. **Dùng `APPEND` trong lúc muốn file đích bằng đúng source.** Tạo nội dung sai.
31. **Sao chép source lên chính source với TRUNCATE_EXISTING.** Nguy cơ mất dữ liệu.
32. **Coi “method return” = “đã ghi bền trên đĩa”.** Cần force/sync riêng khi durability là yêu cầu.
33. **Tin FileChannel luôn nhanh hơn buffered streams với file nhỏ.** Chi phí mở, transfer, caching có thể đảo chiều.
34. **Không xác định ai sở hữu InputStream/OutputStream truyền cho API.** Dễ đóng sớm hoặc rò rỉ.
35. **Không giới hạn byte từ nguồn InputStream do user kiểm soát.** Có thể fill disk/quota.
36. **Cho rằng JVM/GC tự dọn file tạm khi job lỗi.** Cần cleanup/recovery rõ ràng.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Chỉ copy một file trên cùng máy, không cần offset/progress/biến đổi, nên cân nhắc API nào trước?  
**Trả lời:** `Files.copy(source,target)` vì rõ nghĩa và ít code. Benchmark nếu hiệu năng có yêu cầu đặc biệt.

**Câu 2.** Một lượt `in.read(chunk)` trả 123 byte, `chunk.length=65536`. Phải ghi bao nhiêu?  
**Trả lời:** `out.write(chunk,0,123)`, không ghi toàn mảng.

**Câu 3.** `FileChannel.transferTo(0,size,target)` trả nhỏ hơn size có phải bug Java không?  
**Không.** API cho phép partial transfer; phải lặp theo số byte thực chuyển.

**Câu 4.** Nếu `transferTo` trả 0 khi vẫn còn phần cần copy, nên làm gì?  
**Trả lời:** Không spin vô hạn. Xem nguyên nhân, fallback qua ByteBuffer hoặc báo lỗi/đợi readiness tùy loại target.

**Câu 5.** Với file 5 GiB, có được cast `channel.size()` sang `int` không?  
**Không.** Size và offset cần `long`; giới hạn buffer bằng int riêng.

**Câu 6.** `Files.copy(Path,Path)` trả về `long` số bytes phải không?  
**Không.** Nó trả `Path` đích. Các overload từ InputStream hoặc tới OutputStream trả byte count kiểu `long`.

**Câu 7.** BufferedInputStream có luôn tăng tốc khi code đã tự đọc mảng 1 MiB không?  
**Không bảo đảm.** Buffering bổ sung có thể dư; phải đo workload thực.

**Câu 8.** `Files.copy(source,target,COPY_ATTRIBUTES)` có copy mọi extended attributes/ACL trên mọi OS không?  
**Không.** Hỗ trợ và mức chính xác metadata phụ thuộc provider và filesystem.

**Câu 9.** `Files.copy(source,target,REPLACE_EXISTING)` có atomic không?  
**Không được bảo đảm.** Copy có thể là thao tác nhiều bước và để lại partial target khi lỗi.

**Câu 10.** `Files.mismatch(source,target)==-1` chứng minh điều gì?  
**Trả lời:** Hai file có bytes giống nhau tại thời điểm được so sánh theo API; không chứng minh crash durability hay snapshot consistency nếu file bị đổi đồng thời.

**Câu 11.** Vì sao benchmark copy thứ tự cố định có thể không công bằng?  
**Vì** page cache, JIT, hoạt động nền và trạng thái lưu trữ thay đổi giữa lượt, khiến kết quả phụ thuộc thứ tự.

**Câu 12.** `FileChannel.transferTo` có bắt buộc tránh mọi copy trong OS không?  
**Không.** Native/zero-copy là tối ưu khả dĩ, không phải cam kết portable của API.

**Câu 13.** Đã gọi `BufferedOutputStream.flush()`, sau mất điện file chắc chắn đủ bytes không?  
**Không.** Flush tầng Java không đồng nghĩa độ bền storage; cần sync/force phù hợp.

**Câu 14.** Nếu source thay đổi trong lúc copy, Files.copy có cho một snapshot version duy nhất không?  
**Không có bảo đảm chung.** Cần filesystem snapshot, immutable files hoặc giao thức điều phối.

**Câu 15.** Khi cần copy nội dung một directory cùng các subdirectories thì gọi `Files.copy(dir,dest)` một lần đủ không?  
**Không.** Cần duyệt cây và xử lý từng entry, symlink, attributes và lỗi.

**Câu 16.** FileChannel positional `transferTo` có thay đổi position của source FileChannel không?  
**Không.** Offset nguồn được truyền vào, source position không đổi; target có position thì position được cập nhật theo bytes ghi.

## 18. Ghi nhớ và tài liệu chính thức

**Tóm tắt quyết định:**

```text
Cần copy nguyên một file?
    ├── Có, không cần progress/chunk transformation
    │       └── Ưu tiên thử Files.copy(Path,Path,options)
    └── Cần pipeline riêng?
            ├── Chỉ có InputStream/OutputStream hoặc xử lý từng chunk
            │       └── Buffered streams với mảng byte tái sử dụng
            └── Cần offset/random access/transfer giữa channels
                    └── FileChannel + loop partial transfer
                              │
                              └── Đo workload thật trước khi chọn tối ưu
```

Dù chọn cách nào cũng nhớ: **không đọc hết file lớn vào heap chỉ để copy; kiểm tra giá trị số byte thực chuyển; bảo đảm đóng tài nguyên; nhận diện partial copy; phân biệt bytes đã copy, bytes đã kiểm tra và bytes đã ghi bền.**

Tài liệu Java SE 21 chính thức:

- `Files.copy` và các overload/semantics: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html
- `StandardCopyOption` và `LinkOption`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardCopyOption.html và https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/LinkOption.html
- `StandardOpenOption`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardOpenOption.html
- `FileChannel` — `read`, `write`, `transferTo`, `transferFrom`, `size`, `force`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html
- `ByteBuffer` — `flip`, `clear`, `remaining` và direct buffers: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html
- `BufferedInputStream` / `BufferedOutputStream`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/BufferedInputStream.html và https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/BufferedOutputStream.html
- `Files.mismatch` — so sánh contents theo bytes: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#mismatch(java.nio.file.Path,java.nio.file.Path)
