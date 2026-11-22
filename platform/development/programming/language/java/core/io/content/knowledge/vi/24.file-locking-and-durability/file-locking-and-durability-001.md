# FileLock, lock và tryLock trong Java NIO

Khi hai tiến trình cùng đọc hoặc sửa một tệp, mỗi tiến trình có thể ghi những byte hợp lệ nhưng kết quả tổng thể vẫn sai: nội dung bị ghi đè, cập nhật dở dang hoặc một tiến trình đọc giữa lúc tiến trình khác đang thay đổi dữ liệu. `java.nio.channels.FileLock` cung cấp cơ chế **khóa vùng của tệp ở cấp hệ thống tệp** thông qua `FileChannel`. Hai thao tác quan trọng nhất là `lock()` (có thể chờ để lấy khóa) và `tryLock()` (thử lấy ngay).

Hiểu `FileLock` cần phân biệt **khóa độc quyền/chia sẻ**, **xung đột giữa các tiến trình và ngay trong cùng JVM**, **phạm vi byte bị khóa**, **vòng đời khóa**, và giới hạn thực tế của khóa trên từng hệ điều hành. Khóa tệp cũng không tự thay thế đồng bộ giữa các luồng hay bảo đảm dữ liệu đã được ghi bền xuống thiết bị lưu trữ.

## 1. FileLock là gì và dùng khi nào?

`FileLock` mô tả quyền khóa một vùng byte trong tệp mà một `FileChannel` đã mở. Mục tiêu là phối hợp truy cập vào **cùng tệp** giữa các thành phần, thường là các tiến trình khác nhau. Khóa có thể có hai loại:

- **Exclusive lock (khóa độc quyền):** Yêu cầu không có khóa khác xung đột trên cùng vùng. Phù hợp khi một tiến trình đang cập nhật tệp.
- **Shared lock (khóa chia sẻ):** Cho phép các bên cùng giữ khóa chia sẻ nếu hệ thống hỗ trợ, nhưng xung đột với khóa độc quyền trên cùng vùng. Hữu ích khi các bên phối hợp chỉ đọc.

Ví dụ: hai ứng dụng dùng chung `records.dat`. Trước khi cập nhật một bản ghi, chương trình A xin exclusive lock trên vùng byte chứa bản ghi đó. Chương trình B cũng xin exclusive lock cho cùng vùng sẽ phải chờ, thất bại khi thử không chặn, hoặc nhận ngoại lệ tùy trường hợp và API.

Một khóa không tự giải nghĩa các bản ghi, không khôi phục nội dung khi ghi lỗi và không tự kiểm tra tính hợp lệ dữ liệu. Muốn giữ tính nhất quán phải xác định **quy ước tất cả các thành phần cùng tham gia tuân thủ khóa**.

### FileLock không giống khóa luồng Java

`synchronized`, `ReentrantLock` và `FileLock` giải quyết các lớp vấn đề khác nhau:

| Cơ chế | Phạm vi phối hợp | Phù hợp |
| --- | --- | --- |
| `synchronized` hoặc `ReentrantLock` | Các luồng sử dụng cùng quy ước khóa bên trong một JVM | Bảo vệ biến, đối tượng, trình tự thao tác |
| `FileLock` | Khóa tệp qua cơ chế hệ thống, có thể phối hợp nhiều tiến trình | Tránh các tiến trình hợp tác thao tác cùng vùng tệp |
| Ghi file tạm + thay thế có kiểm soát | Quy trình cập nhật toàn bộ file, kiểm soát trạng thái hiển thị | Tránh để file đích bị ghi dở trong một số kịch bản |

Đặc biệt, **khóa tệp được giữ thay cho cả JVM**, không thuộc riêng luồng đã lấy khóa. Vì vậy không dùng `FileLock` làm khóa để điều phối các luồng trong cùng tiến trình. Nhiều luồng của một JVM xin khóa vùng chồng lấn sẽ không đơn giản chờ nhau như `ReentrantLock`.

## 2. Mở FileChannel với quyền phù hợp

Muốn xin khóa bằng `FileChannel`, trước tiên phải mở tệp bằng những `OpenOption` tương thích.

```java
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

// Minh họa trong phương thức xử lý IOException.
Path file = Path.of("records.dat");

try (FileChannel channel = FileChannel.open(
        file,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE,
        StandardOpenOption.CREATE)) {
    // Có thể yêu cầu exclusive lock và thực hiện đọc/ghi.
}
```

Đoạn này chỉ minh họa cách mở: `CREATE` tạo tệp nếu chưa tồn tại; `READ + WRITE` cấp quyền đọc/ghi cho channel. `CREATE` không tạo thư mục cha; nếu đường dẫn không hợp lệ hoặc không có quyền, `open` vẫn có thể ném `IOException`.

Quy tắc quan trọng của `FileChannel.lock(position, size, shared)`:

- **Exclusive lock** (`shared=false`) yêu cầu channel được mở để ghi; nếu không, có thể nhận `NonWritableChannelException`.
- **Shared lock** (`shared=true`) yêu cầu channel được mở để đọc; nếu không, có thể nhận `NonReadableChannelException`.
- Trên một số nền tảng, yêu cầu shared lock có thể được hệ điều hành thực hiện dưới dạng exclusive lock. Vì thế sau khi lấy khóa, nên kiểm tra `fileLock.isShared()` nếu ứng dụng phụ thuộc chặt vào loại khóa được cấp.
- Không suy ra rằng mở tệp bằng `READ` sẽ bảo đảm shared lock được hỗ trợ trên tất cả hệ thống.

Trong trường hợp chỉ quản lý tiến trình ghi, mở channel có `WRITE` và xin exclusive lock thường là lựa chọn đơn giản hơn.

## 3. lock(): xin khóa có thể phải chờ

Các overload thường dùng:

```java
FileLock entire = channel.lock();
FileLock range = channel.lock(100, 50, false);
FileLock shared = channel.lock(0, 1024, true);
```

Đây là các dòng minh họa **cho những lần gọi độc lập** trên channel phù hợp; không chạy cả ba nối tiếp trên cùng tệp khi các vùng chồng lấn. Phải giải phóng khóa trước khi xin khóa xung đột.

- `lock()` tương đương yêu cầu exclusive lock trên vùng từ byte 0 với độ dài `Long.MAX_VALUE`. Vùng này bao phủ mọi byte có thể truy cập của tệp theo ý định khóa toàn bộ.
- `lock(position, size, shared)` xin khóa một vùng liên tục bắt đầu ở byte `position`, độ dài `size`; `shared` chỉ loại khóa được yêu cầu.
- Nếu một tiến trình **khác** đã giữ khóa xung đột, `lock()` thường **chặn luồng gọi** chờ cho đến khi khóa có thể được cấp, bị gián đoạn hoặc có lỗi.
- Nếu **chính JVM hiện tại** đã giữ khóa chồng lấn, hoặc có luồng trong JVM đang chờ khóa chồng lấn, yêu cầu có thể ném `OverlappingFileLockException` ngay thay vì chờ.

Không có timeout tích hợp trong chữ ký `lock()`. Nếu tác vụ có deadline hoặc giao diện cần phản hồi nhanh, cần thiết kế timeout/hủy và điều phối phù hợp; không nên gọi `lock()` trên luồng UI hay event loop không được phép chặn.

Một cách viết an toàn khi muốn giữ exclusive lock trong suốt việc cập nhật:

```java
// Minh họa, file là Path hợp lệ; phương thức cho phép ném IOException.
try (FileChannel channel = FileChannel.open(
        file, StandardOpenOption.READ, StandardOpenOption.WRITE);
     FileLock ignored = channel.lock()) {
    // Thực hiện chuỗi thao tác cập nhật đã được thiết kế.
    // Khóa được giải phóng tự động khi rời try.
}
```

Khối `try-with-resources` giúp tránh quên `release()` khi cập nhật ném ngoại lệ. Tên biến `ignored` chỉ có nghĩa không cần dùng đối tượng khóa trong thân khối; nó vẫn là tài nguyên giữ khóa.

## 4. tryLock(): thử không chờ

Đối với code cần biết ngay khóa có sẵn hay không:

```java
FileLock lock = channel.tryLock();
```

`tryLock()` mặc định xin exclusive lock toàn bộ tệp; `tryLock(position, size, shared)` cho phép xác định vùng và loại khóa. Kết quả gồm:

| Trạng thái | `tryLock()` |
| --- | --- |
| Lấy khóa thành công | Trả về `FileLock` hợp lệ; caller phải giải phóng |
| Một **tiến trình khác** đang giữ khóa xung đột | Trả về `null` thay vì chờ |
| JVM hiện tại đã giữ hoặc đang chờ khóa chồng lấn | Ném `OverlappingFileLockException` |
| Quyền kênh/option không phù hợp | Ném ngoại lệ như `NonWritableChannelException` hoặc `NonReadableChannelException` |
| Kênh đã đóng, lỗi hệ thống tệp hoặc provider không hỗ trợ | Ngoại lệ tương ứng, có thể là `IOException` |

**Đừng viết `channel.tryLock().release()`**: kết quả có thể là `null`. Cũng không nên bắt `OverlappingFileLockException` rồi coi đó là lỗi từ một tiến trình khác; nó chủ yếu báo **xung đột khóa ngay trong JVM hiện tại**.

Mẫu thường dùng:

```java
// Minh họa trong phương thức xử lý IOException.
FileLock acquired = channel.tryLock();
if (acquired == null) {
    System.out.println("File is busy; retry later");
} else {
    try (acquired) {
        // Truy cập dữ liệu cần khóa.
    }
}
```

Ở đây `acquired` là biến được gán một lần nên đủ điều kiện làm tài nguyên trong `try (acquired)` của Java 9+. Với `OverlappingFileLockException`, đoạn code sẽ để ngoại lệ truyền ra ngoài vì đó là tình huống điều phối trong cùng JVM cần xử lý riêng.

### Có nên thử lại nhiều lần?

Trong ứng dụng cần thử lại, nên đặt số lần thử tối đa, deadline, khoảng chờ hoặc exponential backoff và cơ chế hủy. Một vòng `while (channel.tryLock() == null) { }` liên tục có thể chiếm CPU, và còn không xử lý `OverlappingFileLockException`. Nếu file được cập nhật liên tục bởi nhiều tiến trình, một chiến lược retry tốt cũng cần ngăn tình trạng đói tài nguyên (starvation).

## 5. Vùng byte: vị trí và độ dài khóa

Hai đối số `position` và `size` mô tả **vùng byte của file**, không phải `channel.position()` hiện tại và cũng không phải `ByteBuffer.position()`.

Ví dụ:

```text
File:    |--------- bytes 0..99 ---------|---- 100..149 ----|---- 150..199 ----|
Lock A:                                    [100, 150)
Lock B:                                                   [150, 200)
Lock C:                                           [120, 140)
```

- `lock(100, 50, false)` xin khóa các byte từ 100 đến dưới 150 (vùng nửa mở `[100,150)`).
- `lock(150, 50, false)` xin vùng kế tiếp: **không chồng lấn theo tọa độ byte** với vùng trước.
- `lock(120, 20, false)` chồng lấn với khóa đầu tiên và sẽ bị xem là xung đột tùy loại khóa cũng như JVM/tiến trình.
- Hai vùng khóa có thể nằm **sau EOF hiện tại**; vị trí và độ dài vùng khóa không làm tệp tự tăng kích thước.
- Các giá trị âm, phạm vi không hợp lệ hoặc phép cộng `position + size` vượt khả năng biểu diễn được yêu cầu API xử lý bằng ngoại lệ như `IllegalArgumentException`.

Với tệp cố định gồm nhiều bản ghi có cùng kích thước `recordSize`, có thể chọn vùng khóa cho bản ghi `index`:

```java
// Minh họa trong phương thức xử lý IOException.
long offset = Math.multiplyExact(index, recordSize);
try (FileLock recordLock =
        channel.lock(offset, recordSize, false)) {
    // Chỉ cập nhật bản ghi tương ứng.
}
```

Đoạn này giả định `index` và `recordSize` không âm, `recordSize > 0`, channel có quyền ghi và dữ liệu được truy cập bằng quy ước offset chính xác; `Math.multiplyExact` giúp phát hiện tràn trong phép nhân. Còn phải kiểm tra `offset + recordSize` không vượt giới hạn số nguyên dài và tệp có dữ liệu hợp lệ nếu muốn đọc bản ghi đã có.

**Không nên phụ thuộc tuyệt đối vào khóa vùng có độ hạt nhỏ trên mọi nền tảng.** Hệ thống tệp, provider hoặc cách filesystem thực thi locking có thể ảnh hưởng khả năng cấp khóa vùng và cách các ứng dụng ngoài JVM tuân thủ chúng. Khi ứng dụng cần tương thích rộng, hãy kiểm thử cơ chế này trên môi trường triển khai.

## 6. Chương trình Java 17+ hoàn chỉnh: lock, tryLock và xung đột trong một JVM

Ví dụ sau tạo file tạm mới rồi mở **hai FileChannel độc lập trỏ tới cùng file trong một JVM**. Kênh thứ nhất lấy exclusive lock. Kênh thứ hai gọi `tryLock()` khi vùng đã bị khóa, giúp quan sát rằng xung đột **cùng JVM** được báo bằng `OverlappingFileLockException`, không phải `null`. Khi khóa đầu tiên được giải phóng, kênh thứ hai có thể lấy khóa thành công.

Tạo file **`FileLockDemo.java`**:

```java
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class FileLockDemo {
    private FileLockDemo() {}

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("file-lock-demo-", ".bin");
        try {
            try (FileChannel first = FileChannel.open(file,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE);
                 FileChannel second = FileChannel.open(file,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE)) {

                FileLock holder = first.lock();
                try {
                    System.out.println("first valid=" + holder.isValid());
                    System.out.println("first shared=" + holder.isShared());

                    try (FileLock unexpected = second.tryLock()) {
                        // Xung đột trong cùng JVM phải được báo bằng exception.
                        throw new AssertionError("Unexpected overlapping lock");
                    } catch (OverlappingFileLockException expected) {
                        System.out.println("same JVM overlap=exception");
                    }
                } finally {
                    holder.release();
                }

                System.out.println("first after release="
                        + holder.isValid());

                try (FileLock acquired = second.tryLock()) {
                    if (acquired == null) {
                        throw new IOException("File locked by another process");
                    }
                    System.out.println("second acquired=" + acquired.isValid());
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac FileLockDemo.java
java FileLockDemo
```

Kết quả trong môi trường tệp tạm cục bộ hỗ trợ file locking và không có tác nhân bên ngoài can thiệp:

```text
first valid=true
first shared=false
same JVM overlap=exception
first after release=false
second acquired=true
```

Giải thích:

1. `Files.createTempFile` tạo tên tệp mới trong thư mục tạm. Hai kênh dùng cùng đường dẫn nên hai yêu cầu khóa xét cùng file.
2. `first.lock()` xin exclusive lock vùng toàn bộ; `holder.isValid()` là `true` và `holder.isShared()` là `false`.
3. `second.tryLock()` xin exclusive lock chồng lấn trong cùng JVM nên ném `OverlappingFileLockException`, được bắt riêng.
4. `holder.release()` giải phóng khóa; `isValid()` trở thành `false`.
5. Sau giải phóng, `second.tryLock()` lấy exclusive lock. Khối `try-with-resources` đóng đối tượng `FileLock` và các channel theo đúng thứ tự tài nguyên; cuối cùng xóa file tạm.

Ví dụ này **không chứng minh `tryLock()` trả `null` trong xung đột liên tiến trình**. Muốn kiểm thử nhánh đó, cần **hai tiến trình JVM riêng biệt**: tiến trình thứ nhất giữ khóa, tiến trình thứ hai thử khóa cùng vùng khi tiến trình đầu còn giữ. Trên hệ thống hỗ trợ locking phù hợp, lần thử trong tiến trình thứ hai trả `null`. Không giả lập việc này bằng hai `FileChannel` trong cùng JVM rồi chờ `null`.

## 7. Giải phóng khóa và quản lý vòng đời

Đối tượng `FileLock` cung cấp:

| API | Ý nghĩa |
| --- | --- |
| `position()` | Vị trí bắt đầu của vùng đã xin khóa |
| `size()` | Độ dài vùng khóa |
| `isShared()` | Cho biết khóa được cấp là shared hay exclusive |
| `isValid()` | Có còn hiệu lực theo trạng thái API hay không |
| `release()` | Yêu cầu giải phóng khóa |
| `close()` | Là phương thức `AutoCloseable` giúp giải phóng trong `try-with-resources` |
| `acquiredBy()` | Trả về channel đã cấp khóa |

Một khóa hợp lệ tồn tại đến khi được `release()`, channel chứa nó bị đóng hoặc JVM kết thúc (tùy cơ chế giải phóng hệ thống). `FileLock.isValid()` dùng kiểm tra trạng thái đã biết, nhưng không phải cam kết bất biến nếu tài nguyên bị đóng đồng thời.

Cần đặc biệt lưu ý: trên **một số hệ điều hành**, đóng *bất kỳ channel nào* tới cùng file có thể giải phóng **tất cả khóa mà JVM đang giữ trên file đó**, kể cả các khóa được lấy bằng channel khác. Do đó không mở/đóng nhiều channel vào cùng file một cách tùy tiện trong khi đang dựa vào khóa của một channel khác. Nếu nghiệp vụ nhạy cảm, quản lý quyền sở hữu file/channel và thời gian giữ khóa thật rõ ràng, đồng thời kiểm thử trên môi trường chạy.

Mẫu đóng khóa nên ưu tiên:

```java
// Minh họa: file là Path; cần IOException handling.
try (FileChannel channel = FileChannel.open(file,
        StandardOpenOption.READ, StandardOpenOption.WRITE);
     FileLock lock = channel.lock()) {
    // Truy cập tài nguyên được phối hợp theo quy ước.
}
// Lock được giải phóng, channel được đóng.
```

Tuy nhiên, nếu code trong phạm vi khóa tạo thêm view/mapping hoặc truyền tài nguyên cho luồng khác, cần bảo đảm không để luồng khác tiếp tục thao tác sau khi khóa đã được giải phóng.

## 8. Ngoại lệ và tình huống chờ khóa

| Tình huống | Phản ứng API |
| --- | --- |
| Một khóa vùng trùng trong cùng JVM | `OverlappingFileLockException` |
| `lock()` phải đợi tiến trình khác | Luồng có thể chặn đến khi khóa được cấp hoặc có lỗi |
| `tryLock()` gặp khóa xung đột ở tiến trình khác | `null` |
| Exclusive lock từ channel không cho ghi | `NonWritableChannelException` |
| Shared lock từ channel không cho đọc | `NonReadableChannelException` |
| Luồng bị interrupt trong khi `lock()` đang chờ | Có thể ném `FileLockInterruptionException` |
| Channel bị đóng trong khi luồng đang chờ lock | Có thể ném `AsynchronousCloseException` |
| File/channel gặp lỗi I/O | `IOException` hoặc lớp con phù hợp |
| Tọa độ vùng khóa không hợp lệ | `IllegalArgumentException` |
| Channel đã đóng trước thao tác | Thường `ClosedChannelException` |

Với tác vụ nền, sự gián đoạn và đóng channel cần được xử lý có chủ đích. Tránh bắt mọi exception rồi ghi log "file đang bận": `OverlappingFileLockException` là dấu hiệu quản lý khóa trong JVM; `IOException` có thể là lỗi thiết bị hay mất quyền; còn `null` từ `tryLock()` mới là trường hợp thử không chặn bị một tiến trình khác giữ khóa theo hợp đồng API.

Nếu cần chờ hữu hạn thay vì chờ vô hạn, một vòng thử theo deadline trên `tryLock()` có thể dễ điều khiển hơn `lock()`, nhưng phải giảm tần suất thử, xử lý interrupt và phân biệt rõ null/exception.

## 9. Giới hạn của FileLock trong thực tế

### 9.1. Khóa advisory và mandatory

Không phải mọi hệ thống bắt buộc các thao tác đọc/ghi thông thường phải tuân thủ `FileLock`. Có hệ thống thực thi **advisory locks**: chỉ các chương trình cùng tham gia quy ước khóa mới tránh xung đột. Có hệ thống hỗ trợ hoặc dùng **mandatory locks** trong một số chế độ. Java không hứa một hành vi cưỡng chế giống nhau trên tất cả provider/file system.

Hệ quả: nếu ứng dụng A giữ exclusive lock nhưng một công cụ khác bỏ qua quy ước khóa và ghi trực tiếp, hành vi có thể khác tùy môi trường. **Không dựa vào FileLock như hàng rào bảo mật bắt buộc** chống mọi ứng dụng khác; cần phân quyền file, giao thức sở hữu và kiểm thử thực tế.

### 9.2. Không phải transaction, không bảo đảm atomicity hay durability

Lấy khóa thành công **không tự**:

- Kết hợp nhiều lệnh `channel.write()` thành một giao dịch không thể bị chia nhỏ.
- Ngăn hệ điều hành hoặc thiết bị gặp lỗi khi ghi.
- Phục hồi dữ liệu khi tiến trình chết giữa chừng.
- Đảm bảo dữ liệu đã xuống bộ nhớ bền vững của thiết bị.

Đối với dữ liệu quan trọng, ngoài quy ước khóa có thể phải dùng `FileChannel.force(boolean)` theo yêu cầu durability, ghi file tạm rồi thay thế với chính sách riêng, hoặc cấu trúc ghi nhật ký có khả năng khôi phục. `force` cũng có phạm vi cam kết tùy thiết bị/provider; nó không thay thế việc quản lý khóa và khôi phục lỗi.

### 9.3. Khóa tệp và memory-mapped buffer

`FileChannel.map()` tạo ánh xạ tệp vào bộ nhớ; các thao tác truy cập vùng được ánh xạ có thể có hành vi tương tác với file locks phụ thuộc hệ điều hành. **Không mặc định khóa FileLock sẽ ngăn mọi thao tác đọc/ghi vào vùng mapping trên tất cả nền tảng.** Nếu ứng dụng dùng cả mapping và locking, phải thiết kế/kiểm thử giao thức đồng bộ riêng.

### 9.4. NFS, SMB, container và giới hạn hệ điều hành

File locking phụ thuộc provider, khả năng filesystem và đôi khi cả cấu hình mạng. Trên network filesystem hoặc môi trường nhiều container, cách thực thi và xử lý mất kết nối có thể khác với đĩa cục bộ. Phải kiểm tra trên đúng hạ tầng sử dụng, nhất là khi khóa dùng như cơ chế bảo vệ job chạy độc quyền hoặc dữ liệu ghi bởi nhiều máy.

Giữ khóa quá lâu cũng có thể giảm throughput và dẫn đến deadlock nghiệp vụ nếu nhiều file/lock được xin theo những thứ tự khác nhau. Khi cần khóa nhiều tài nguyên, hãy chọn thứ tự cố định, phạm vi nhỏ nhất đủ an toàn và luôn giải phóng qua `try-with-resources`.

## 10. Cách dùng FileLock để đảm bảo một tiến trình chủ sở hữu

Một trường hợp thường gặp là chỉ cho một phiên xử lý cập nhật một file dữ liệu tại một thời điểm. Ví dụ logic:

1. Mở channel với `READ/WRITE` phù hợp, bảo đảm file lock có vị trí lưu trữ dùng chung giữa các tiến trình cần phối hợp.
2. Gọi `tryLock()`. Nếu nhận `null`, ứng dụng có thể dừng hoặc lên lịch thử lại thay vì chờ.
3. Nếu nhận `FileLock`, giữ khóa trong toàn bộ khoảng đọc, xác minh, cập nhật và kiểm tra kết quả liên quan.
4. Trong `finally` hoặc `try-with-resources`, giải phóng khóa và đóng channel. Ghi nhận riêng lỗi I/O thay vì bỏ qua.

Mẫu này đòi hỏi mọi tiến trình tham gia dùng chung một quy ước locking. Nếu không bảo đảm được cùng đường dẫn vật lý/file system hoặc cùng hành vi provider, một distributed lock hoặc cơ chế điều phối ngoài file có thể cần thiết.

Một **lock file** riêng (ví dụ `worker.lock`) có thể giúp tránh đụng trực tiếp file dữ liệu, nhưng quy trình không được **xóa lock file rồi tạo lại** khi một tiến trình khác đang giữ khóa cũ: việc xóa/tạo lại có thể dẫn tới hai file object khác nhau tại cùng tên đường dẫn, phá giả định tất cả bên đang khóa cùng một đối tượng. Hãy phân biệt file tồn tại trên đường dẫn và khóa OS đang giữ trên file object.

## 11. Lỗi phổ biến và cách tránh

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chờ `tryLock()` như thể đó là `lock()` | Không chờ; kết quả null nếu tiến trình khác giữ khóa | Xử lý null hoặc dùng `lock()` khi thật sự muốn chờ |
| Cho rằng cùng JVM giữ khóa chồng lấn sẽ khiến `tryLock()` trả null | Nhận `OverlappingFileLockException` | Điều phối bằng khóa luồng Java, phân biệt lỗi nội JVM |
| Dùng `FileLock` thay `ReentrantLock` trong đa luồng | Race/deadlock nghiệp vụ, exception vùng chồng lấn | Dùng cơ chế đồng bộ luồng riêng |
| Xin exclusive lock trên read-only channel | `NonWritableChannelException` | Mở channel có quyền WRITE |
| Nghĩ shared lock chắc chắn được hỗ trợ | Khóa thực tế có thể là exclusive | Kiểm tra `isShared()` |
| Quên `release()` hay không đóng channel | Giữ khóa/tài nguyên quá lâu | `try-with-resources` |
| Giữ một khóa rồi tự do đóng channel khác tới cùng tệp | Một số hệ thống có thể giải phóng khóa ngoài ý muốn | Tập trung quản lý channel và khóa |
| Khóa một vùng nhưng ghi ngoài vùng đó | Dữ liệu ngoài phạm vi khóa không được bảo vệ theo quy ước | Tính offset/size rõ ràng và kiểm tra nghiệp vụ |
| Tin rằng FileLock bắt buộc mọi phần mềm khác tuân theo | Tiến trình không hợp tác vẫn có thể sửa tệp trên hệ thống advisory | Phân quyền và cùng quy ước locking |
| Tin rằng khóa = ghi bền | Crash vẫn có thể làm mất/cắt dở dữ liệu | Tách locking, force, ghi tạm và recovery |
| Spin vòng lặp gọi `tryLock()` khi bận | Tiêu tốn CPU và có thể gây starvation | Deadline, retry/backoff và cơ chế hủy |

**Ghi nhớ:** `FileChannel.lock()` yêu cầu khóa và có thể chờ tiến trình khác; `tryLock()` trả ngay khi không thể lấy khóa từ tiến trình khác, nhưng vẫn có thể ném `OverlappingFileLockException` khi chồng lấn trong cùng JVM. `FileLock` bảo vệ **vùng byte theo quy ước locking của hệ thống**, cần quản lý quyền mở channel, loại khóa, độ dài vùng khóa, lỗi, vòng đời và phối hợp giữa các tiến trình.